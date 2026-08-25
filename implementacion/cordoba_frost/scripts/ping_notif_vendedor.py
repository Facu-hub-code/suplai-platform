#!/usr/bin/env python3
"""Diagnóstico: salud WABA + ping plantilla UTILITY y texto sesión a un vendedor."""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import asyncpg
import certifi
from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV = ROOT.parent / "backend-supabase" / ".env"
TENANT_ID = "be6e832f-bf4b-4ce2-b6e6-52e89824bc89"
GRAPH = "https://graph.facebook.com/v21.0"
DEFAULT_TO = "5493585098671"
TEMPLATE = "suplai_nuevo_pedido_vendedor_v2"
CTX = ssl.create_default_context(cafile=certifi.where())

load_dotenv(BACKEND_ENV)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def fernet() -> Fernet:
    key = (os.getenv("CREDENTIALS_MASTER_KEY") or "").strip()
    if not key:
        raise SystemExit("Falta CREDENTIALS_MASTER_KEY")
    return Fernet(key.encode("utf-8"))


def graph_get(url: str, token: str, params: dict | None = None) -> tuple[int, dict]:
    q = urllib.parse.urlencode(params or {})
    full = f"{url}?{q}" if q else url
    req = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def graph_post(url: str, token: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def summarize_health(health: dict) -> dict:
    """Saca canary_id / entidades con errores sin dump enorme."""
    entities = health.get("entities") or []
    issues = []
    for ent in entities:
        errors = ent.get("errors") or []
        if not errors and ent.get("canary_id") is None:
            continue
        issues.append(
            {
                "entity_type": ent.get("entity_type"),
                "canary_id": ent.get("canary_id"),
                "errors": [
                    {"code": e.get("error_code"), "message": str(e.get("error_description") or "")[:180]}
                    for e in errors
                ],
            }
        )
    return {"canary_id": health.get("canary_id"), "entities_with_errors": issues}


async def load_secrets() -> dict[str, str]:
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        raise SystemExit("Falta SUPABASE_DB_URL_POOLER")
    fr = fernet()
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            """
            SELECT name, value_enc
            FROM public.tenant_secrets
            WHERE tenant_id = $1::uuid AND name = ANY($2::text[])
            """,
            TENANT_ID,
            [
                "whatsapp.long_live_token",
                "whatsapp.waba",
                "whatsapp.phone_id",
            ],
        )
        return {r["name"]: fr.decrypt(r["value_enc"].encode()).decode() for r in rows}
    finally:
        await conn.close()


def ping_dest(token: str, phone_id: str, to: str) -> None:
    tpl_payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": TEMPLATE,
            "language": {"code": "es_AR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "TEST"},
                        {"type": "text", "text": "ping"},
                        {"type": "text", "text": f"Prueba notificacion vendedor a {to}."},
                        {"type": "text", "text": "$1"},
                        {"type": "text", "text": "Retiro en sucursal"},
                    ],
                }
            ],
        },
    }
    st, body = graph_post(f"{GRAPH}/{phone_id}/messages", token, tpl_payload)
    err = (body.get("error") or {}) if isinstance(body, dict) else {}
    wamid = ((body.get("messages") or [{}])[0].get("id") if isinstance(body, dict) else None)
    print(
        f"[send-template {to}] HTTP {st} wamid={wamid} "
        f"code={err.get('code')} sub={err.get('error_subcode')} msg={str(err.get('message') or '')[:220]}"
    )

    text_payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": f"Ping Córdoba Frost (texto sesión) a {to}. Si llega este y no la plantilla, el fallo es HSM/pago Meta.",
        },
    }
    st, body = graph_post(f"{GRAPH}/{phone_id}/messages", token, text_payload)
    err = (body.get("error") or {}) if isinstance(body, dict) else {}
    wamid = ((body.get("messages") or [{}])[0].get("id") if isinstance(body, dict) else None)
    print(
        f"[send-text {to}] HTTP {st} wamid={wamid} "
        f"code={err.get('code')} sub={err.get('error_subcode')} msg={str(err.get('message') or '')[:220]}"
    )


async def main() -> int:
    dests = [d for d in sys.argv[1:] if d.strip()] or [DEFAULT_TO]
    secrets = await load_secrets()
    token = secrets.get("whatsapp.long_live_token") or ""
    waba = secrets.get("whatsapp.waba") or ""
    phone_id = secrets.get("whatsapp.phone_id") or ""
    if not token or not waba or not phone_id:
        print("[FAIL] faltan token, waba o phone_id")
        return 1

    print(f"[*] dests={dests}  waba_len={len(waba)}  phone_id_len={len(phone_id)}")

    st, waba_info = graph_get(
        f"{GRAPH}/{waba}",
        token,
        {
            "fields": "id,name,account_review_status,business_verification_status,health_status",
        },
    )
    print(f"[waba] HTTP {st} review={waba_info.get('account_review_status')} verify={waba_info.get('business_verification_status')}")
    if isinstance(waba_info.get("health_status"), dict):
        print(f"[waba] health={json.dumps(summarize_health(waba_info['health_status']), ensure_ascii=False)}")
    elif waba_info.get("error"):
        print(f"[waba] error={json.dumps(waba_info.get('error'), ensure_ascii=False)[:400]}")

    st, phones = graph_get(
        f"{GRAPH}/{waba}/phone_numbers",
        token,
        {"fields": "id,display_phone_number,verified_name,quality_rating,status,code_verification_status"},
    )
    print(f"[phones] HTTP {st}")
    for p in phones.get("data") or []:
        print(
            f"    display={p.get('display_phone_number')} status={p.get('status')} "
            f"quality={p.get('quality_rating')} verified={p.get('verified_name')}"
        )
    if phones.get("error"):
        print(f"[phones] error={json.dumps(phones.get('error'), ensure_ascii=False)[:400]}")

    st, tpls = graph_get(
        f"{GRAPH}/{waba}/message_templates",
        token,
        {"name": TEMPLATE, "fields": "name,status,language,category,rejected_reason"},
    )
    print(f"[tpl] HTTP {st}")
    for t in tpls.get("data") or []:
        print(
            f"    {t.get('name')} lang={t.get('language')} status={t.get('status')} "
            f"cat={t.get('category')} rejected={t.get('rejected_reason')}"
        )
    if tpls.get("error"):
        print(f"[tpl] error={json.dumps(tpls.get('error'), ensure_ascii=False)[:400]}")

    for dest in dests:
        ping_dest(token, phone_id, dest)
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
