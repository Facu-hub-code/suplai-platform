"""Monitor de caídas de los servicios de Suplai en Railway (DEV-20).

Corre por fuera de Railway (GitHub Actions, cada 5 minutos). Pega al /health
del backend, el agente y el MCP. Un servicio está caído cuando falla dos
chequeos seguidos (el segundo se hace en la misma corrida, tras una espera).

Ante una caída crea una issue urgente en el proyecto P3 de Linear, o comenta
la que ya está abierta para ese servicio, y manda un mail por Brevo. Cuando el
servicio vuelve, comenta la recuperación sin cerrar la issue.

El estado entre corridas vive en la propia issue: la descripción lleva la línea
`clave: health:<servicio>` y cada comentario del monitor lleva una línea
`estado: caido` o `estado: recuperado`. El último estado manda.

Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

LINEAR_URL = "https://api.linear.app/graphql"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

SERVICIOS: dict[str, str] = {
    "backend": "https://web-production-f544f.up.railway.app/health",
    "agente": "https://agente-conversacional-multitenant-production.up.railway.app/health",
    "mcp": "https://mcp.suplaisales.com/health",
}
NOMBRES = {"backend": "Backend", "agente": "Agente de WhatsApp", "mcp": "Servidor MCP"}

ETIQUETAS = ("Detectada", "infra", "Bug")
MAIL_DESTINO = "facundo@suplaisales.com"
CAIDO = "caido"
RECUPERADO = "recuperado"


def log(msg: str) -> None:
    print(msg, flush=True)


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@dataclass
class Config:
    linear_key: str
    team_id: str
    project_id: str
    brevo_key: str
    mail_desde: str
    mail_destino: str
    dry_run: bool
    timeout: float
    espera_reintento: float
    run_url: str

    @classmethod
    def desde_env(cls, env: dict[str, str] | None = None) -> "Config":
        e = os.environ if env is None else env
        return cls(
            linear_key=e.get("LINEAR_API_KEY", "").strip(),
            team_id=e.get("LINEAR_TEAM_ID", "").strip(),
            project_id=e.get("LINEAR_PROJECT_ID", "").strip(),
            brevo_key=e.get("BREVO_API_KEY", "").strip(),
            mail_desde=e.get("BREVO_SENDER_EMAIL", "").strip(),
            mail_destino=e.get("MONITOR_MAIL_TO", "").strip() or MAIL_DESTINO,
            dry_run=e.get("MONITOR_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "si"),
            timeout=float(e.get("MONITOR_TIMEOUT", "") or 15),
            espera_reintento=float(e.get("MONITOR_RETRY_DELAY", "") or 60),
            run_url=e.get("MONITOR_RUN_URL", "").strip(),
        )

    def faltantes(self) -> list[str]:
        if self.dry_run:
            return []
        pares = {
            "LINEAR_API_KEY": self.linear_key,
            "LINEAR_TEAM_ID": self.team_id,
            "LINEAR_PROJECT_ID": self.project_id,
            "BREVO_API_KEY": self.brevo_key,
            "BREVO_SENDER_EMAIL": self.mail_desde,
        }
        return [k for k, v in pares.items() if not v]


def servicios_desde_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """URLs por defecto, pisables con MONITOR_URL_<SERVICIO> (para probar una caída)."""
    e = os.environ if env is None else env
    return {s: (e.get(f"MONITOR_URL_{s.upper()}", "").strip() or url) for s, url in SERVICIOS.items()}


# --- HTTP ---

def _http_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        return err.code, None


def chequear(url: str, timeout: float) -> str | None:
    """None si el servicio responde 2xx; si no, un motivo corto sin datos sensibles."""
    req = urllib.request.Request(url, headers={"user-agent": "suplai-monitor-caidas"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return None
            return f"HTTP {resp.status}"
    except urllib.error.HTTPError as err:
        return f"HTTP {err.code}"
    except urllib.error.URLError as err:
        return f"sin conexión ({type(err.reason).__name__})"
    except TimeoutError:
        return f"timeout ({timeout:.0f} s)"
    except OSError as err:
        return f"error de red ({type(err).__name__})"


def chequear_servicios(
    urls: dict[str, str], timeout: float, espera: float, dormir: Callable[[float], None] = time.sleep
) -> dict[str, str | None]:
    """Caído solo si fallan dos chequeos seguidos: los que fallan se reintentan tras una espera."""
    primeros = {s: chequear(url, timeout) for s, url in urls.items()}
    fallidos = [s for s, motivo in primeros.items() if motivo is not None]
    if not fallidos:
        return primeros
    for s in fallidos:
        log(f"{s}: primer chequeo falló ({primeros[s]}); reintento en {espera:.0f} s")
    dormir(espera)
    return {s: (chequear(urls[s], timeout) if s in fallidos else None) for s in urls}


# --- Linear ---

class Linear:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._labels: list[str] | None = None

    def gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        status, data = _http_json(
            LINEAR_URL,
            {"query": query, "variables": variables},
            {"authorization": self.cfg.linear_key},
            self.cfg.timeout,
        )
        if status != 200 or not isinstance(data, dict) or data.get("errors"):
            # No se loguea el cuerpo: puede traer datos de la cuenta.
            raise RuntimeError(f"Linear respondió HTTP {status}")
        return data["data"]

    def buscar_abierta(self, servicio: str) -> dict[str, Any] | None:
        q = """
        query($project: ID!, $clave: String!) {
          issues(first: 5, filter: {
            project: { id: { eq: $project } },
            state: { type: { nin: ["completed", "canceled"] } },
            description: { contains: $clave }
          }) {
            nodes { id identifier url comments(first: 100) { nodes { body createdAt } } }
          }
        }"""
        nodes = self.gql(q, {"project": self.cfg.project_id, "clave": clave(servicio)})["issues"]["nodes"]
        return nodes[0] if nodes else None

    def etiquetas(self) -> list[str]:
        if self._labels is None:
            q = """
            query($nombres: [String!]) {
              issueLabels(first: 50, filter: { name: { in: $nombres } }) {
                nodes { id name isGroup team { id } }
              }
            }"""
            nodes = self.gql(q, {"nombres": list(ETIQUETAS)})["issueLabels"]["nodes"]
            ids = []
            for nombre in ETIQUETAS:
                candidatos = [n for n in nodes if n["name"] == nombre and not n.get("isGroup")]
                # Preferimos la etiqueta del team; si no, la del workspace.
                candidatos.sort(key=lambda n: (n.get("team") or {}).get("id") != self.cfg.team_id)
                if candidatos:
                    ids.append(candidatos[0]["id"])
                else:
                    log(f"aviso: no encontré la etiqueta {nombre!r} en Linear")
            self._labels = ids
        return self._labels

    def crear(self, titulo: str, descripcion: str) -> dict[str, Any]:
        q = """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) { success issue { id identifier url } }
        }"""
        entrada = {
            "teamId": self.cfg.team_id,
            "projectId": self.cfg.project_id,
            "title": titulo,
            "description": descripcion,
            "priority": 1,
            "labelIds": self.etiquetas(),
        }
        return self.gql(q, {"input": entrada})["issueCreate"]["issue"]

    def comentar(self, issue_id: str, cuerpo: str) -> None:
        q = """
        mutation($input: CommentCreateInput!) {
          commentCreate(input: $input) { success }
        }"""
        self.gql(q, {"input": {"issueId": issue_id, "body": cuerpo}})


def clave(servicio: str) -> str:
    return f"clave: health:{servicio}"


def ultimo_estado(issue: dict[str, Any]) -> str:
    """Estado según el último comentario del monitor; la issue nace en `caido`."""
    comentarios = sorted(issue.get("comments", {}).get("nodes", []), key=lambda c: c.get("createdAt", ""))
    estado = CAIDO
    for c in comentarios:
        for linea in (c.get("body") or "").splitlines():
            linea = linea.strip().strip("`").lower()
            if linea in (f"estado: {CAIDO}", f"estado: {RECUPERADO}"):
                estado = linea.split(": ", 1)[1]
    return estado


# --- Mail ---

def mandar_mail(cfg: Config, asunto: str, texto: str) -> None:
    status, _ = _http_json(
        BREVO_URL,
        {
            "sender": {"email": cfg.mail_desde, "name": "Suplai monitor"},
            "to": [{"email": cfg.mail_destino}],
            "subject": asunto,
            "textContent": texto,
        },
        {"api-key": cfg.brevo_key, "accept": "application/json"},
        cfg.timeout,
    )
    if status not in (200, 201, 202):
        raise RuntimeError(f"Brevo respondió HTTP {status}")


# --- Textos ---

def texto_caida(servicio: str, url: str, motivo: str, cfg: Config) -> str:
    lineas = [
        f"El monitor externo detectó que **{NOMBRES[servicio]}** no responde.",
        "",
        f"- URL chequeada: {url}",
        f"- Motivo: {motivo} (dos chequeos seguidos)",
        f"- Cuándo: {ahora()}",
    ]
    if cfg.run_url:
        lineas.append(f"- Corrida: {cfg.run_url}")
    return "\n".join(lineas)


def descripcion_issue(servicio: str, url: str, motivo: str, cfg: Config) -> str:
    return "\n".join([
        texto_caida(servicio, url, motivo, cfg),
        "",
        "Cuando vuelva, el monitor lo comenta acá. La issue no se cierra sola.",
        "",
        f"`{clave(servicio)}`",
    ])


# --- Lógica principal ---

def procesar(servicio: str, url: str, motivo: str | None, cfg: Config, linear: Linear | None) -> str:
    """Decide y ejecuta la acción para un servicio. Devuelve la acción tomada."""
    caido = motivo is not None
    if cfg.dry_run and linear is None:
        accion = "crear_issue+mail" if caido else "nada"
        log(f"[dry-run] {servicio}: {'caído: ' + motivo if caido else 'ok'} → {accion}")
        return accion

    assert linear is not None
    issue = linear.buscar_abierta(servicio)
    estado = ultimo_estado(issue) if issue else None

    if caido and issue is None:
        accion = "crear_issue+mail"
    elif caido and estado == RECUPERADO:
        accion = "comentar_caida+mail"
    elif caido:
        accion = "sigue_caido"
    elif issue is not None and estado == CAIDO:
        accion = "comentar_recuperacion"
    else:
        accion = "nada"

    ref = issue["identifier"] if issue else "-"
    log(f"{servicio}: {'caído: ' + motivo if caido else 'ok'} (issue {ref}, estado {estado}) → {accion}")
    if cfg.dry_run:
        return accion

    titulo = f"Caída: {NOMBRES[servicio]} no responde"
    if accion == "crear_issue+mail":
        issue = linear.crear(titulo, descripcion_issue(servicio, url, motivo, cfg))
        log(f"{servicio}: creé {issue['identifier']}")
    elif accion == "comentar_caida+mail":
        linear.comentar(issue["id"], f"Se volvió a caer.\n\n{texto_caida(servicio, url, motivo, cfg)}\n\nestado: {CAIDO}")
    elif accion == "comentar_recuperacion":
        linear.comentar(issue["id"], f"**{NOMBRES[servicio]}** volvió a responder ({ahora()}).\n\nestado: {RECUPERADO}")

    if accion.endswith("+mail"):
        cuerpo = f"{texto_caida(servicio, url, motivo, cfg)}\n\nIssue: {issue['url']}".replace("**", "")
        mandar_mail(cfg, f"[Suplai] Caída: {NOMBRES[servicio]} no responde", cuerpo)
        log(f"{servicio}: mail enviado")
    return accion


def main(env: dict[str, str] | None = None) -> int:
    cfg = Config.desde_env(env)
    faltan = cfg.faltantes()
    if faltan:
        log(f"error: faltan variables {', '.join(faltan)}; no se chequea nada")
        return 2

    linear = Linear(cfg) if cfg.linear_key and cfg.project_id else None
    urls = servicios_desde_env(env)
    resultados = chequear_servicios(urls, cfg.timeout, cfg.espera_reintento)

    errores = 0
    for servicio, motivo in resultados.items():
        try:
            procesar(servicio, urls[servicio], motivo, cfg, linear)
        except Exception as err:  # Seguimos con los otros servicios.
            errores += 1
            log(f"error procesando {servicio}: {err}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
