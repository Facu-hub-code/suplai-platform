#!/usr/bin/env python3
"""Crea 4 plantillas MARKETING de combos helados en el WABA de cordoba_frost."""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
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
INPUT = Path(__file__).resolve().parents[1] / "inputs" / "combos-helados-agosto-2026"
SCHEMA = "cordoba_frost"
TENANT_ID = "be6e832f-bf4b-4ce2-b6e6-52e89824bc89"
GRAPH = "https://graph.facebook.com/v21.0"
CTX = ssl.create_default_context(cafile=certifi.where())

load_dotenv(BACKEND_ENV)

FOOTER = "Córdoba Frost · Solares 1163"

TEMPLATES = [
    {
        "name": "cf_helados_xsell_inicial",
        "image_key": "inicial",
        "body": (
            "Hola 👋 Somos Córdoba Frost.\n\n"
            "Además de la panadería congelada, ahora tenemos combos de helados para kiosco y almacén. "
            "Cerrados, listos para vender.\n\n"
            "🍦 Inicial $75.500\n"
            "🍦 Medio $118.400\n"
            "🍦 Premium $158.400\n\n"
            "El de la foto es el Inicial: vasos, palitos, banana split, bombón, Barra Brava y Carita Tiki.\n\n"
            "¿Cuál te armo?"
        ),
        "buttons": ["Combo Inicial", "Combo Medio", "Combo Premium"],
    },
    {
        "name": "cf_helados_retarget_inicial",
        "image_key": "inicial",
        "body": (
            "Hola 👋 Vimos que te interesaron los helados y no llegamos a cerrar.\n\n"
            "Te dejo el Combo Inicial ($75.500):\n"
            "• 10 vasos 330 cc\n"
            "• Palito agua uva y frutilla\n"
            "• Banana Split x20\n"
            "• Bombón crocante x8\n"
            "• Barra Brava x20\n"
            "• Carita Tiki frutilla x28\n\n"
            "Es un combo cerrado, sin armar a medida. ¿Lo dejamos confirmado?"
        ),
        "buttons": ["Lo quiero", "Ver otro combo", "Seguimos mañana"],
    },
    {
        "name": "cf_helados_retarget_medio",
        "image_key": "medio",
        "body": (
            "Hola 👋 Retomamos tu consulta de helados.\n\n"
            "Combo Medio ($118.400):\n"
            "• Golden Croky, Cassata, HIT y Tiki\n"
            "• Bombón crocante y Fortachón\n"
            "• 15 vasos 330 cc\n"
            "• Banana Split, Camely cheesecake y barrita Dubai\n\n"
            "Todo cerrado, listo para exhibir. ¿Seguimos con este?"
        ),
        "buttons": ["Lo quiero", "Ver otro combo", "Seguimos mañana"],
    },
    {
        "name": "cf_helados_retarget_premium",
        "image_key": "premium",
        "body": (
            "Hola 👋 Quedó pendiente el combo de helados.\n\n"
            "Combo Premium ($158.400):\n"
            "• Alfajor blanco + HIT\n"
            "• Banabana, granizado, Kamikaze, Cassata y Fripper\n"
            "• Fortachón, Tiki choco/vainilla y bombón\n"
            "• 20 vasos, Golden Croky y barrita Dubai\n\n"
            "Es el más completo de la campaña. ¿Lo armamos?"
        ),
        "buttons": ["Lo quiero", "Ver otro combo", "Seguimos mañana"],
    },
]

IMAGES = {
    "inicial": INPUT / "combo-inicial.png",
    "medio": INPUT / "combo-medio.png",
    "premium": INPUT / "combo-premium.png",
}


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def fernet() -> Fernet:
    key = (os.getenv("CREDENTIALS_MASTER_KEY") or "").strip()
    if not key:
        raise SystemExit("Falta CREDENTIALS_MASTER_KEY")
    return Fernet(key.encode("utf-8"))


def looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return value.strip().startswith("+") or (len(digits) >= 10 and not digits.startswith("1") and " " in value)


def graph_get(url: str, token: str, params: dict | None = None) -> dict:
    q = urllib.parse.urlencode(params or {})
    full = f"{url}?{q}" if q else url
    req = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
        return json.loads(resp.read().decode())


def graph_post_json(url: str, token: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
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


def upload_header_handle(app_id: str, token: str, file_bytes: bytes, file_name: str, mime: str) -> str:
    params = urllib.parse.urlencode(
        {"file_name": file_name, "file_length": len(file_bytes), "file_type": mime}
    )
    start_url = f"{GRAPH}/{app_id}/uploads?{params}"
    req = urllib.request.Request(start_url, data=b"", headers={"Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
        session_id = json.loads(resp.read().decode()).get("id")
    if not session_id:
        raise RuntimeError("Meta no devolvió sesión de upload")
    upload_url = f"{GRAPH}/{session_id}"
    req2 = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            "Authorization": f"OAuth {token}",
            "file_offset": "0",
            "Content-Type": "application/octet-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=60, context=CTX) as resp2:
        handle = json.loads(resp2.read().decode()).get("h")
    if not handle:
        raise RuntimeError("Meta no devolvió header_handle")
    return str(handle)


def upload_supabase(path: str, file_bytes: bytes, mime: str) -> str:
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    url = f"{base}/storage/v1/object/meta_templates_media/{path}"
    req = urllib.request.Request(
        url,
        data=file_bytes,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": mime,
            "x-upsert": "true",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
        resp.read()
    return f"{base}/storage/v1/object/public/meta_templates_media/{path}"


def components(body: str, buttons: list[str], header_handle: str) -> list[dict]:
    return [
        {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": [header_handle]}},
        {"type": "BODY", "text": body},
        {"type": "FOOTER", "text": FOOTER},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": t} for t in buttons],
        },
    ]


async def main() -> int:
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        print("[FAIL] falta SUPABASE_DB_URL_POOLER")
        return 1
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
            ["whatsapp.long_live_token", "whatsapp.waba", "whatsapp.client_id"],
        )
        secrets = {r["name"]: fr.decrypt(r["value_enc"].encode()).decode() for r in rows}
    finally:
        await conn.close()

    token = secrets.get("whatsapp.long_live_token") or ""
    waba = secrets.get("whatsapp.waba") or ""
    client_id = (secrets.get("whatsapp.client_id") or "").strip()
    if not token or not waba:
        print("[FAIL] faltan token o waba")
        return 1

    dbg = graph_get(f"{GRAPH}/debug_token", token, {"input_token": token, "access_token": token})
    app_id = str((dbg.get("data") or {}).get("app_id") or "")
    if not app_id:
        print("[FAIL] debug_token no devolvió app_id")
        return 1
    print(f"[*] Graph app_id ok (len={len(app_id)})")
    if looks_like_phone(client_id) or client_id != app_id:
        print("[*] whatsapp.client_id no era el App ID de Graph; se actualiza para poder subir imágenes desde el backoffice")
        conn = await asyncpg.connect(db_url, statement_cache_size=0)
        try:
            await conn.execute(
                """
                UPDATE public.tenant_secrets
                SET value_enc = $1, updated_at = NOW()
                WHERE tenant_id = $2::uuid AND name = 'whatsapp.client_id'
                """,
                fr.encrypt(app_id.encode()).decode(),
                TENANT_ID,
            )
        finally:
            await conn.close()

    handles: dict[str, str] = {}
    media_urls: dict[str, str] = {}
    ts = int(time.time())
    for key, path in IMAGES.items():
        raw = path.read_bytes()
        fname = f"cordoba_frost_{ts}_{key}.png"
        print(f"[*] Meta upload {key} ({len(raw)} bytes)")
        handles[key] = upload_header_handle(app_id, token, raw, fname, "image/png")
        storage_path = f"{SCHEMA}/{fname}"
        media_urls[key] = upload_supabase(storage_path, raw, "image/png")
        print(f"    handle ok · storage {storage_path}")

    results = []
    for tpl in TEMPLATES:
        img = tpl["image_key"]
        payload = {
            "name": tpl["name"],
            "language": "es",
            "category": "MARKETING",
            "components": components(tpl["body"], tpl["buttons"], handles[img]),
        }
        print(f"[*] create {tpl['name']}")
        status, body = graph_post_json(f"{GRAPH}/{waba}/message_templates", token, payload)
        meta_status = (body.get("status") if isinstance(body, dict) else None) or (body.get("error") if isinstance(body, dict) else body)
        print(f"    HTTP {status} · {json.dumps(body, ensure_ascii=False)[:400]}")
        results.append({"name": tpl["name"], "http": status, "meta": body, "media_url": media_urls[img]})
        if status in (200, 201):
            conn = await asyncpg.connect(db_url, statement_cache_size=0)
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO public.meta_plantillas (tenant_id, template_name, category, variable_columns, media_url)
                    VALUES ($1::uuid, $2, 'MARKETING', '[]'::jsonb, $3)
                    ON CONFLICT (tenant_id, template_name) DO UPDATE SET
                        category = EXCLUDED.category,
                        media_url = COALESCE(EXCLUDED.media_url, public.meta_plantillas.media_url)
                    RETURNING id, template_name, media_url
                    """,
                    TENANT_ID,
                    tpl["name"],
                    media_urls[img],
                )
                print(f"    db {row['id']}")
            finally:
                await conn.close()

    out = Path(__file__).resolve().parents[1] / "outputs" / "phase-08-plantillas-helados-agosto-2026.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[*] resumen {out}")
    failed = [r for r in results if r["http"] not in (200, 201)]
    return 1 if failed else 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
