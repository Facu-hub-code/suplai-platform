"""Tests del monitor de caídas. Sin red: urlopen, Linear y Brevo van con mocks.

Correr con: python -m unittest discover -s infra/monitor-caidas -v
"""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

import monitor

ENV_OK = {
    "LINEAR_API_KEY": "lin_test",
    "LINEAR_TEAM_ID": "team-1",
    "LINEAR_PROJECT_ID": "proj-1",
    "BREVO_API_KEY": "brevo_test",
    "BREVO_SENDER_EMAIL": "monitor@example.com",
    "MONITOR_RETRY_DELAY": "0",
}


class Respuesta:
    def __init__(self, status: int, body: bytes = b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def cfg(**extra) -> monitor.Config:
    return monitor.Config.desde_env({**ENV_OK, **extra})


def issue(*estados: str, identifier: str = "DEV-900") -> dict:
    comentarios = [
        {"body": f"texto\n\nestado: {e}", "createdAt": f"2026-11-03T10:0{i}:00Z"}
        for i, e in enumerate(estados)
    ]
    return {"id": "iss-1", "identifier": identifier, "url": "https://linear.app/x/DEV-900", "comments": {"nodes": comentarios}}


class ChequeoTest(unittest.TestCase):
    def test_2xx_es_ok(self):
        with mock.patch("urllib.request.urlopen", return_value=Respuesta(200)):
            self.assertIsNone(monitor.chequear("https://x/health", 1))

    def test_http_error_da_motivo(self):
        err = urllib.error.HTTPError("https://x", 502, "Bad Gateway", {}, io.BytesIO(b"secreto"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(monitor.chequear("https://x/health", 1), "HTTP 502")

    def test_sin_conexion_no_filtra_detalle(self):
        err = urllib.error.URLError(ConnectionRefusedError("detalle interno"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            motivo = monitor.chequear("https://x/health", 1)
        self.assertEqual(motivo, "sin conexión (ConnectionRefusedError)")

    def test_timeout(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            self.assertEqual(monitor.chequear("https://x/health", 3), "timeout (3 s)")

    def test_un_fallo_suelto_no_es_caida(self):
        dormir = mock.Mock()
        with mock.patch.object(monitor, "chequear", side_effect=[None, "HTTP 500", None]) as ch:
            res = monitor.chequear_servicios({"a": "u1", "b": "u2"}, 1, 30, dormir)
        self.assertEqual(res, {"a": None, "b": None})
        dormir.assert_called_once_with(30)
        self.assertEqual(ch.call_count, 3)

    def test_dos_fallos_seguidos_es_caida(self):
        with mock.patch.object(monitor, "chequear", side_effect=["HTTP 500", "HTTP 503"]):
            res = monitor.chequear_servicios({"a": "u1"}, 1, 0, mock.Mock())
        self.assertEqual(res, {"a": "HTTP 503"})

    def test_todo_ok_no_espera(self):
        dormir = mock.Mock()
        with mock.patch.object(monitor, "chequear", return_value=None):
            monitor.chequear_servicios({"a": "u1", "b": "u2"}, 1, 30, dormir)
        dormir.assert_not_called()


class EstadoTest(unittest.TestCase):
    def test_issue_sin_comentarios_esta_caida(self):
        self.assertEqual(monitor.ultimo_estado(issue()), monitor.CAIDO)

    def test_manda_el_ultimo_comentario(self):
        self.assertEqual(monitor.ultimo_estado(issue("caido", "recuperado")), monitor.RECUPERADO)
        self.assertEqual(monitor.ultimo_estado(issue("recuperado", "caido")), monitor.CAIDO)

    def test_ignora_comentarios_humanos(self):
        i = issue("recuperado")
        i["comments"]["nodes"].append({"body": "lo estoy mirando", "createdAt": "2026-11-03T11:00:00Z"})
        self.assertEqual(monitor.ultimo_estado(i), monitor.RECUPERADO)


class ProcesarTest(unittest.TestCase):
    def setUp(self):
        self.linear = mock.Mock(spec=monitor.Linear)
        self.linear.crear.return_value = {"id": "nuevo", "identifier": "DEV-901", "url": "https://linear.app/x/DEV-901"}
        p = mock.patch.object(monitor, "mandar_mail")
        self.mail = p.start()
        self.addCleanup(p.stop)

    def test_caida_nueva_crea_issue_y_manda_mail(self):
        self.linear.buscar_abierta.return_value = None
        accion = monitor.procesar("backend", "https://b/health", "HTTP 502", cfg(), self.linear)
        self.assertEqual(accion, "crear_issue+mail")
        titulo, desc = self.linear.crear.call_args.args
        self.assertIn("Backend", titulo)
        self.assertIn("clave: health:backend", desc)
        self.assertIn("HTTP 502", desc)
        self.linear.comentar.assert_not_called()
        asunto, cuerpo = self.mail.call_args.args[1:]
        self.assertIn("Backend", asunto)
        self.assertIn("DEV-901", cuerpo)

    def test_sigue_caido_no_repite(self):
        self.linear.buscar_abierta.return_value = issue()
        accion = monitor.procesar("agente", "https://a/health", "HTTP 502", cfg(), self.linear)
        self.assertEqual(accion, "sigue_caido")
        self.linear.crear.assert_not_called()
        self.linear.comentar.assert_not_called()
        self.mail.assert_not_called()

    def test_recaida_comenta_en_la_abierta(self):
        self.linear.buscar_abierta.return_value = issue("recuperado")
        accion = monitor.procesar("mcp", "https://m/health", "timeout (15 s)", cfg(), self.linear)
        self.assertEqual(accion, "comentar_caida+mail")
        self.linear.crear.assert_not_called()
        issue_id, cuerpo = self.linear.comentar.call_args.args
        self.assertEqual(issue_id, "iss-1")
        self.assertTrue(cuerpo.endswith("estado: caido"))
        self.mail.assert_called_once()

    def test_recuperacion_comenta_sin_mail(self):
        self.linear.buscar_abierta.return_value = issue()
        accion = monitor.procesar("backend", "https://b/health", None, cfg(), self.linear)
        self.assertEqual(accion, "comentar_recuperacion")
        self.assertTrue(self.linear.comentar.call_args.args[1].endswith("estado: recuperado"))
        self.mail.assert_not_called()

    def test_ya_recuperado_no_hace_nada(self):
        self.linear.buscar_abierta.return_value = issue("recuperado")
        self.assertEqual(monitor.procesar("backend", "u", None, cfg(), self.linear), "nada")
        self.linear.comentar.assert_not_called()

    def test_dry_run_con_linear_solo_lee(self):
        self.linear.buscar_abierta.return_value = None
        accion = monitor.procesar("backend", "u", "HTTP 500", cfg(MONITOR_DRY_RUN="1"), self.linear)
        self.assertEqual(accion, "crear_issue+mail")
        self.linear.crear.assert_not_called()
        self.mail.assert_not_called()

    def test_dry_run_sin_linear(self):
        c = monitor.Config.desde_env({"MONITOR_DRY_RUN": "1"})
        self.assertEqual(monitor.procesar("backend", "u", "HTTP 500", c, None), "crear_issue+mail")
        self.mail.assert_not_called()


class LinearTest(unittest.TestCase):
    def test_crear_usa_prioridad_1_y_etiquetas(self):
        llamadas = []

        def fake_http(url, body, headers, timeout):
            llamadas.append((url, body, headers))
            if "issueLabels" in body["query"]:
                return 200, {"data": {"issueLabels": {"nodes": [
                    {"id": "g", "name": "Detectada", "isGroup": True, "team": None},
                    {"id": "det", "name": "Detectada", "isGroup": False, "team": {"id": "team-1"}},
                    {"id": "inf", "name": "infra", "isGroup": False, "team": {"id": "team-1"}},
                    {"id": "bug-ws", "name": "Bug", "isGroup": False, "team": None},
                    {"id": "bug", "name": "Bug", "isGroup": False, "team": {"id": "team-1"}},
                ]}}}
            return 200, {"data": {"issueCreate": {"success": True, "issue": {"id": "n", "identifier": "DEV-1", "url": "u"}}}}

        with mock.patch.object(monitor, "_http_json", side_effect=fake_http):
            monitor.Linear(cfg()).crear("t", "d")
        url, body, headers = llamadas[-1]
        self.assertEqual(url, monitor.LINEAR_URL)
        self.assertEqual(headers["authorization"], "lin_test")
        entrada = body["variables"]["input"]
        self.assertEqual(entrada["priority"], 1)
        self.assertEqual(entrada["projectId"], "proj-1")
        self.assertEqual(entrada["teamId"], "team-1")
        self.assertEqual(entrada["labelIds"], ["det", "inf", "bug"])

    def test_buscar_filtra_por_clave_y_abiertas(self):
        with mock.patch.object(monitor, "_http_json", return_value=(200, {"data": {"issues": {"nodes": []}}})) as h:
            self.assertIsNone(monitor.Linear(cfg()).buscar_abierta("mcp"))
        body = h.call_args.args[1]
        self.assertEqual(body["variables"], {"project": "proj-1", "clave": "clave: health:mcp"})
        self.assertIn('nin: ["completed", "canceled"]', body["query"])

    def test_error_de_linear_no_expone_cuerpo(self):
        with mock.patch.object(monitor, "_http_json", return_value=(200, {"errors": [{"message": "token lin_test inválido"}]})):
            with self.assertRaises(RuntimeError) as ctx:
                monitor.Linear(cfg()).buscar_abierta("mcp")
        self.assertNotIn("lin_test", str(ctx.exception))


class MailTest(unittest.TestCase):
    def test_mail_por_brevo(self):
        with mock.patch.object(monitor, "_http_json", return_value=(201, None)) as h:
            monitor.mandar_mail(cfg(), "asunto", "texto")
        url, body, headers, _ = h.call_args.args
        self.assertEqual(url, monitor.BREVO_URL)
        self.assertEqual(headers["api-key"], "brevo_test")
        self.assertEqual(body["to"], [{"email": "facundo@suplaisales.com"}])
        self.assertEqual(body["sender"]["email"], "monitor@example.com")

    def test_mail_fallido_lanza(self):
        with mock.patch.object(monitor, "_http_json", return_value=(401, None)):
            with self.assertRaises(RuntimeError):
                monitor.mandar_mail(cfg(), "a", "t")


class MainTest(unittest.TestCase):
    def test_faltan_secrets_no_chequea(self):
        with mock.patch.object(monitor, "chequear_servicios") as ch:
            self.assertEqual(monitor.main({}), 2)
        ch.assert_not_called()

    def test_url_pisable_para_probar_caida(self):
        urls = monitor.servicios_desde_env({"MONITOR_URL_BACKEND": "https://httpbin.org/status/503"})
        self.assertEqual(urls["backend"], "https://httpbin.org/status/503")
        self.assertEqual(urls["mcp"], monitor.SERVICIOS["mcp"])

    def test_dry_run_completo_sin_red_externa(self):
        def fake_urlopen(req, timeout):
            if "web-production" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 503, "x", {}, io.BytesIO(b""))
            return Respuesta(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             mock.patch.object(monitor, "_http_json") as http, \
             mock.patch("builtins.print") as p:
            rc = monitor.main({"MONITOR_DRY_RUN": "1", "MONITOR_RETRY_DELAY": "0"})
        self.assertEqual(rc, 0)
        http.assert_not_called()
        salida = "\n".join(str(c.args[0]) for c in p.call_args_list)
        self.assertIn("[dry-run] backend: caído: HTTP 503 → crear_issue+mail", salida)
        self.assertIn("[dry-run] agente: ok → nada", salida)

    def test_un_servicio_con_error_no_frena_a_los_otros(self):
        with mock.patch.object(monitor, "chequear_servicios", return_value={"backend": "HTTP 500", "agente": None, "mcp": None}), \
             mock.patch.object(monitor, "procesar", side_effect=[RuntimeError("Linear respondió HTTP 500"), "nada", "nada"]) as pr, \
             mock.patch("builtins.print"):
            self.assertEqual(monitor.main(ENV_OK), 1)
        self.assertEqual(pr.call_count, 3)


if __name__ == "__main__":
    unittest.main()
