#!/usr/bin/env python3
"""Prueba Meta de dimer_litoral_contacto_v2 y agenda puntual 14:00 Chile.

Schema: dimer. Pooler 6543, statement_cache_size=0.
No imprime tokens. El INSERT de agenda solo corre si Meta acepta el send de prueba.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import asyncpg
import certifi
from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV = ROOT.parent / "backend-supabase" / ".env"
OUT = Path(__file__).resolve().parents[1] / "outputs"
SCHEMA = "dimer"
TENANT_ID = "02a0c4e0-8ac7-4bf1-aee9-19b44a14f66a"
TEMPLATE_NAME = "dimer_litoral_contacto_v2"
GRAPH = "https://graph.facebook.com/v21.0"
CTX = ssl.create_default_context(cafile=certifi.where())
TEST_TO = "5493585098671"
# Params reales de campaña, eligiendo el vendedor con más tildes/espacios.
TEST_PARAMS = ["Facundo", "María Verónica Montes", "+56 9 5814 2220"]
AGENDA_DATE = date(2026, 9, 7)
AGENDA_TIME = "14:00"
GRUPO_ID = 12
ORIGEN = "dimer-litoral-contacto-v2"

load_dotenv(BACKEND_ENV)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def graph_request(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def sanitize_param(text: str) -> str:
    cleaned = (text or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = re.sub(r" {4,}", "   ", cleaned)
    return cleaned.strip()


async def load_secrets(conn: asyncpg.Connection) -> dict[str, str]:
    key = (os.getenv("CREDENTIALS_MASTER_KEY") or "").strip()
    if not key:
        raise SystemExit("Falta CREDENTIALS_MASTER_KEY")
    fr = Fernet(key.encode("utf-8"))
    rows = await conn.fetch(
        """
        SELECT name, value_enc
        FROM public.tenant_secrets
        WHERE tenant_id = $1::uuid AND name = ANY($2::text[])
        """,
        TENANT_ID,
        ["whatsapp.long_live_token", "whatsapp.waba", "whatsapp.phone_id"],
    )
    secrets = {r["name"]: fr.decrypt(r["value_enc"].encode()).decode() for r in rows}
    missing = [n for n in ("whatsapp.long_live_token", "whatsapp.waba", "whatsapp.phone_id") if not secrets.get(n)]
    if missing:
        raise SystemExit(f"Faltan secretos WhatsApp de dimer: {missing}")
    return secrets


def fetch_template(token: str, waba: str) -> dict:
    status, body = graph_request(
        "GET",
        f"{GRAPH}/{waba}/message_templates?name={TEMPLATE_NAME}&fields=name,status,language,category,rejected_reason,components",
        token,
    )
    items = body.get("data") or []
    item = items[0] if items else {}
    return {"http": status, "item": item, "count": len(items)}


def send_test(token: str, phone_id: str, language: str) -> dict:
    params = [sanitize_param(p) for p in TEST_PARAMS]
    payload = {
        "messaging_product": "whatsapp",
        "to": TEST_TO,
        "type": "template",
        "template": {
            "name": TEMPLATE_NAME,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ],
        },
    }
    print(f"[*] send prueba → {TEST_TO} lang={language} params={params}", flush=True)
    status, body = graph_request("POST", f"{GRAPH}/{phone_id}/messages", token, payload)
    err = (body.get("error") or {}) if isinstance(body, dict) else {}
    return {
        "http": status,
        "accepted": status == 200,
        "message_id": ((body.get("messages") or [{}])[0] or {}).get("id") if status == 200 else None,
        "meta_code": err.get("code"),
        "meta_subcode": err.get("error_subcode"),
        "meta_message": (err.get("message") or "")[:300],
        "user_title": err.get("error_user_title"),
        "user_msg": err.get("error_user_msg"),
        "params": params,
        "language": language,
    }


async def create_agenda(conn: asyncpg.Connection) -> dict:
    print("Schema: dimer (repetido). INSERT agenda puntual Litoral 14:00.", flush=True)
    row = await conn.fetchrow(
        """
        INSERT INTO dimer.agenda (
            grupo_id, meta_plantilla_id, tipo, hora_envio,
            fecha_programada, dynamic_params, activo, origen
        )
        SELECT
            $1::int,
            mp.id,
            'puntual',
            TIME '14:00',
            $2::date,
            '[]'::jsonb,
            true,
            $3
        FROM public.meta_plantillas mp
        WHERE mp.tenant_id = $4::uuid
          AND mp.template_name = $5
          AND NOT EXISTS (
              SELECT 1 FROM dimer.agenda a
              WHERE a.grupo_id = $1
                AND a.meta_plantilla_id = mp.id
                AND a.tipo = 'puntual'
                AND a.fecha_programada = $2::date
                AND a.hora_envio = TIME '14:00'
          )
        RETURNING id, hora_envio::text, fecha_programada, activo, origen
        """,
        GRUPO_ID,
        AGENDA_DATE,
        ORIGEN,
        TENANT_ID,
        TEMPLATE_NAME,
    )
    if row:
        return {"created": True, **dict(row)}
    existing = await conn.fetchrow(
        """
        SELECT a.id, a.hora_envio::text, a.fecha_programada, a.activo, a.origen, a.enviado_at
        FROM dimer.agenda a
        JOIN public.meta_plantillas mp ON mp.id = a.meta_plantilla_id
        WHERE a.grupo_id = $1
          AND mp.template_name = $2
          AND a.tipo = 'puntual'
          AND a.fecha_programada = $3::date
          AND a.hora_envio = TIME '14:00'
        LIMIT 1
        """,
        GRUPO_ID,
        TEMPLATE_NAME,
        AGENDA_DATE,
    )
    return {"created": False, "existing": dict(existing) if existing else None}


async def main() -> int:
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        print("[FAIL] falta SUPABASE_DB_URL_POOLER")
        return 1
    print("Schema: dimer. Prueba Meta + agenda Litoral v2.", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0, timeout=30, command_timeout=60)
    try:
        secrets = await load_secrets(conn)
        tpl = fetch_template(secrets["whatsapp.long_live_token"], secrets["whatsapp.waba"])
        item = tpl.get("item") or {}
        meta_status = item.get("status")
        language = item.get("language") or "es"
        print(f"[*] plantilla {TEMPLATE_NAME} status={meta_status} language={language}", flush=True)
        if meta_status != "APPROVED":
            summary = {
                "schema": SCHEMA,
                "template": {"name": TEMPLATE_NAME, "status": meta_status, "language": language, "http": tpl["http"]},
                "send": None,
                "agenda": None,
                "verdict": "blocked_template_not_approved",
            }
            (OUT / "litoral-prueba-y-agenda-v2.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print(f"[FAIL] plantilla no APPROVED: {meta_status}")
            return 1

        send = send_test(secrets["whatsapp.long_live_token"], secrets["whatsapp.phone_id"], language)
        print(
            f"    HTTP {send['http']} accepted={send['accepted']} "
            f"code={send.get('meta_code')} msg={send.get('meta_message')}",
            flush=True,
        )
        agenda = None
        if send["accepted"]:
            agenda = await create_agenda(conn)
            print(f"[*] agenda {agenda}", flush=True)
        else:
            print("[SKIP] no se crea agenda porque Meta rechazó la prueba", flush=True)

        summary = {
            "schema": SCHEMA,
            "template": {"name": TEMPLATE_NAME, "status": meta_status, "language": language},
            "send": send,
            "agenda": agenda,
            "verdict": "ok" if send["accepted"] else "meta_rejected_test",
        }
        out = OUT / "litoral-prueba-y-agenda-v2.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[*] resumen {out}", flush=True)
        return 0 if send["accepted"] else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
