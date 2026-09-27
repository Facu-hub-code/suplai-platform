#!/usr/bin/env python3
"""Sondeo de la API Sistel de Distribuidora Rawson.

Login JWT, descubrimiento de vistas y muestra de filas por alias.
No escribe en Supabase: solo deja evidencia en outputs/ para decidir el mapeo.

Credenciales en implementacion/rawson/.env (ignorado por git):

    python3 implementacion/rawson/scripts/probe_sistel.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TENANT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = TENANT_DIR / "outputs"


def cargar_env(path: Path) -> None:
    """Lee el .env sin pasar por el shell: la contraseña trae |, # y $."""
    if not path.exists():
        return
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


cargar_env(TENANT_DIR / ".env")

BASE_URL = os.environ.get("SISTEL_BASE_URL", "").rstrip("/")
USERNAME = os.environ.get("SISTEL_USER", "")
PASSWORD = os.environ.get("SISTEL_PASS", "")
TIMEOUT = int(os.environ.get("SISTEL_TIMEOUT", "30"))

# El host es DNS dinámico (selfip.net, TTL 60) y algunos resolvers de ISP
# devuelven la IP de parking en vez de la real. Resolvemos por DNS-over-HTTPS
# y pegamos contra la IP con cabecera Host.
HOST_REAL = urllib.parse.urlsplit(BASE_URL).hostname or ""
IP_EFECTIVA = ""

# Alias conocidos + candidatos a tantear si GET /vistas no los expone.
ALIAS_SEMILLA = "raw_productos"
ALIAS_CANDIDATOS = [
    "raw_productos",
    "raw_clientes",
    "raw_vendedores",
    "raw_precios",
    "raw_listas_precios",
    "raw_stock",
    "raw_pedidos",
]


def resolver_doh(host: str) -> str:
    """IP del host según Google DoH, ignorando el resolver del sistema."""
    url = f"https://dns.google/resolve?name={urllib.parse.quote(host)}&type=A"
    try:
        import ssl

        try:
            import certifi

            contexto = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            contexto = ssl.create_default_context()
        with urllib.request.urlopen(url, timeout=10, context=contexto) as resp:
            payload = json.load(resp)
    except Exception as exc:
        print(f"[dns] DoH falló ({type(exc).__name__}: {exc}) — se usa el resolver del sistema")
        return ""
    for respuesta in payload.get("Answer") or []:
        if respuesta.get("type") == 1:
            return respuesta.get("data", "")
    return ""


def preflight() -> None:
    """Compara DNS local vs DoH y tantea el puerto antes de gastar el login."""
    global IP_EFECTIVA

    import socket

    try:
        ip_local = socket.gethostbyname(HOST_REAL)
    except OSError as exc:
        ip_local = f"error: {exc}"
    ip_doh = resolver_doh(HOST_REAL)

    print(f"[dns] {HOST_REAL} → local={ip_local}  doh={ip_doh or 'n/d'}")
    if ip_doh and ip_doh != ip_local:
        print(f"[dns] discrepancia: se fuerza {ip_doh} con cabecera Host: {HOST_REAL}")
        IP_EFECTIVA = ip_doh

    destino = IP_EFECTIVA or (ip_local if not ip_local.startswith("error") else "")
    puerto = urllib.parse.urlsplit(BASE_URL).port or 80
    if not destino:
        return
    sock = socket.socket()
    sock.settimeout(8)
    try:
        sock.connect((destino, puerto))
        print(f"[tcp] {destino}:{puerto} abierto")
    except Exception as exc:
        print(f"[tcp] {destino}:{puerto} sin conexión — {type(exc).__name__}: {exc}")
        print("[tcp] el host filtra el puerto: pedir a Sistel whitelist de la IP de salida")
    finally:
        sock.close()


def _request(method: str, path: str, *, token: str | None = None, body: dict | None = None):
    if IP_EFECTIVA:
        partes = urllib.parse.urlsplit(BASE_URL)
        autoridad = f"{IP_EFECTIVA}:{partes.port}" if partes.port else IP_EFECTIVA
        url = f"{partes.scheme}://{autoridad}{path}"
    else:
        url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if IP_EFECTIVA:
        req.add_header("Host", HOST_REAL)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw[:2000]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:2000]
    except Exception as exc:  # timeout, DNS, TLS
        return 0, f"{type(exc).__name__}: {exc}"


def login() -> str:
    status, payload = _request(
        "POST", "/auth/login", body={"username": USERNAME, "password": PASSWORD}
    )
    if status != 200 or not isinstance(payload, dict):
        print(f"[login] HTTP {status}: {payload}")
        sys.exit(1)
    token = payload.get("access_token") or payload.get("token")
    if not token:
        print(f"[login] sin access_token en la respuesta: {list(payload)}")
        sys.exit(1)
    print(f"[login] OK — claves de respuesta: {sorted(payload)}")
    return token


def descubrir_vistas(token: str) -> dict:
    status, payload = _request("GET", "/vistas", token=token)
    print(f"[vistas] HTTP {status}")
    if status == 200:
        (OUT_DIR / "erp-sistel-vistas.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if isinstance(payload, dict):
            print(f"[vistas] {len(payload)} alias: {sorted(payload)[:30]}")
        return payload if isinstance(payload, dict) else {}
    print(f"[vistas] respuesta: {payload}")
    return {}


def muestrear(token: str, alias: str, limit: int = 5) -> dict:
    qs = urllib.parse.urlencode({"page": 1, "limit": limit})
    status, payload = _request("GET", f"/vistas/{alias}?{qs}", token=token)
    resultado: dict = {"alias": alias, "status": status}

    if status != 200:
        resultado["error"] = payload if isinstance(payload, str) else json.dumps(payload)[:500]
        print(f"[{alias}] HTTP {status} — {resultado['error'][:160]}")
        return resultado

    # Modo simple devuelve {data, pagination}; flexible puede devolver un arreglo suelto.
    if isinstance(payload, dict) and "data" in payload:
        filas = payload.get("data") or []
        resultado["modo"] = "simple"
        resultado["pagination"] = payload.get("pagination")
    else:
        filas = payload if isinstance(payload, list) else []
        resultado["modo"] = "flexible"

    resultado["filas_muestra"] = len(filas)
    resultado["columnas"] = sorted(filas[0]) if filas and isinstance(filas[0], dict) else []
    resultado["muestra"] = filas[:3]

    print(f"[{alias}] OK modo={resultado['modo']} filas={len(filas)} cols={len(resultado['columnas'])}")
    if resultado["columnas"]:
        print(f"[{alias}] columnas: {resultado['columnas']}")
    return resultado


def main() -> None:
    faltantes = [k for k, v in
                 (("SISTEL_BASE_URL", BASE_URL), ("SISTEL_USER", USERNAME), ("SISTEL_PASS", PASSWORD))
                 if not v]
    if faltantes:
        print(f"Faltan variables de entorno: {', '.join(faltantes)}")
        sys.exit(2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Base: {BASE_URL}  usuario: {USERNAME}")

    preflight()
    token = login()
    vistas = descubrir_vistas(token)

    alias_a_probar = list(vistas) if vistas else ALIAS_CANDIDATOS
    if ALIAS_SEMILLA not in alias_a_probar:
        alias_a_probar.insert(0, ALIAS_SEMILLA)

    reporte = {"base_url": BASE_URL, "vistas": vistas, "sondeos": []}
    for alias in alias_a_probar:
        reporte["sondeos"].append(muestrear(token, alias))

    destino = OUT_DIR / "erp-sistel-probe.json"
    destino.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReporte: {destino}")


if __name__ == "__main__":
    main()
