#!/usr/bin/env python3
"""Crea 7 plantillas IMAGE (1 por promo nueva) + 1 carrusel en el WABA de gonzales."""
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
INPUT = Path(__file__).resolve().parents[1] / "inputs" / "promos-arcor-nuevas"
OUT = Path(__file__).resolve().parents[1] / "outputs" / "promos-arcor-nuevas"
SCHEMA = "gonzales"
TENANT_ID = "48132ae5-2383-4f3b-86f5-050b2d62a09b"
GRAPH = "https://graph.facebook.com/v21.0"
CTX = ssl.create_default_context(cafile=certifi.where())

load_dotenv(BACKEND_ENV)

PROMOS = [
    {
        "key": "mixto",
        "file": "tere04-triples-mixto.jpeg",
        "image_name": "gg_promo_triples_mixto_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte la promo Triples Mixto: 15% off llevando "
            "3 Mini Torta clásico, 3 brownie, 3 Bon o Bon y 3 Cofler Block. ¿Te armo el combo?"
        ),
        "card_body": "Triples Mixto 15% off. 3 clásico + 3 brownie + 3 Bon o Bon + 3 Cofler.",
        "cta": "Quiero Mixto",
    },
    {
        "key": "rellenas",
        "file": "tere06-galletas-rellenas.jpeg",
        "image_name": "gg_promo_galletas_rellenas_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte la promo Galletas Rellenas: 15% off con "
            "3 Sonrisa, 3 Merengadas, 2 Rumba, 2 Amor y 2 Mellizas. ¿Te armo el combo?"
        ),
        "card_body": "Galletas rellenas 15% off. Sonrisa, Merengadas, Rumba, Amor y Mellizas.",
        "cta": "Quiero Rellenas",
    },
    {
        "key": "diversion",
        "file": "tere08-surtido-diversion.jpeg",
        "image_name": "gg_promo_surtido_diversion_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte Surtido Diversión 400 g: 15% off llevando 10 unidades. ¿Te lo armo?"
        ),
        "card_body": "Surtido Diversión 400 g. 15% off en 10 unidades.",
        "cta": "Quiero Diversión",
    },
    {
        "key": "bagley",
        "file": "tere09-triples-bagley.jpeg",
        "image_name": "gg_promo_triples_bagley_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte Triples Bagley: 15% off con 6 Chocotorta, "
            "3 Blanco y Negro negro y 3 blanco. ¿Te armo el combo?"
        ),
        "card_body": "Triples Bagley 15% off. 6 Chocotorta + 3 BYN negro + 3 blanco.",
        "cta": "Quiero Triples Bagley",
    },
    {
        "key": "rex",
        "file": "tere10-rex-kesitas.jpeg",
        "image_name": "gg_promo_rex_kesitas_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte Rex + Kesitas 75 g: 15% off llevando 6 de cada uno. ¿Te armo el combo?"
        ),
        "card_body": "Rex + Kesitas 75 g. 15% off. 6 + 6.",
        "cta": "Quiero Rex",
    },
    {
        "key": "cofler",
        "file": "tere11-cofler-block.jpeg",
        "image_name": "gg_promo_cofler_block_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte Cofler Block 38 g: 10% off llevando 10 unidades. ¿Te lo armo?"
        ),
        "card_body": "Cofler Block 38 g. 10% off en 10 unidades.",
        "cta": "Quiero Cofler",
    },
    {
        "key": "menthoplus",
        "file": "tere14-menthoplus.jpeg",
        "image_name": "gg_promo_menthoplus_v1",
        "image_body": (
            "Hola {{1}}, {{2}} te comparte Menthoplus: 15% off con 1 display Cherry, 1 Strong y 1 Menta. ¿Te armo el combo?"
        ),
        "card_body": "Menthoplus 15% off. Cherry + Strong + Menta.",
        "cta": "Quiero Menthoplus",
    },
]

CAROUSEL_NAME = "gg_carousel_promos_arcor_v2"
CAROUSEL_INTRO = (
    "Hola {{1}}, {{2}} te comparte las super promos Arcor nuevas. Deslizá y tocá la que te sirva."
)
BODY_EXAMPLE = [["Facundo", "Gabriela"]]
VARIABLE_COLUMNS = ["nombre", "vendedor"]
IMAGE_BUTTONS = ["Me interesa", "No me interesa"]


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
        with urllib.request.urlopen(req, timeout=90, context=CTX) as resp:
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
    with urllib.request.urlopen(req2, timeout=90, context=CTX) as resp2:
        handle = json.loads(resp2.read().decode()).get("h")
    if not handle:
        raise RuntimeError("Meta no devolvió header_handle")
    return str(handle)


def upload_supabase(path: str, file_bytes: bytes, mime: str) -> str:
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not key:
        raise SystemExit("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
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


def image_components(body: str, header_handle: str) -> list[dict]:
    return [
        {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": [header_handle]}},
        {"type": "BODY", "text": body, "example": {"body_text": BODY_EXAMPLE}},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": t} for t in IMAGE_BUTTONS],
        },
    ]


def carousel_components(handles: dict[str, str]) -> list[dict]:
    cards = []
    for promo in PROMOS:
        cards.append(
            {
                "components": [
                    {
                        "type": "HEADER",
                        "format": "IMAGE",
                        "example": {"header_handle": [handles[promo["key"]]]},
                    },
                    {"type": "BODY", "text": promo["card_body"]},
                    {
                        "type": "BUTTONS",
                        "buttons": [{"type": "QUICK_REPLY", "text": promo["cta"]}],
                    },
                ]
            }
        )
    return [
        {"type": "BODY", "text": CAROUSEL_INTRO, "example": {"body_text": BODY_EXAMPLE}},
        {"type": "CAROUSEL", "cards": cards},
    ]


async def upsert_plantilla(conn, name: str, media_url: str | None) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO public.meta_plantillas (tenant_id, template_name, category, variable_columns, media_url)
        VALUES ($1::uuid, $2, 'MARKETING', $3::jsonb, $4)
        ON CONFLICT (tenant_id, template_name) DO UPDATE SET
            category = EXCLUDED.category,
            variable_columns = EXCLUDED.variable_columns,
            media_url = COALESCE(EXCLUDED.media_url, public.meta_plantillas.media_url)
        RETURNING id::text
        """,
        TENANT_ID,
        name,
        json.dumps(VARIABLE_COLUMNS),
        media_url,
    )
    return str(row["id"])


async def main() -> int:
    for promo in PROMOS:
        if len(promo["cta"]) > 25:
            print(f"[FAIL] CTA > 25 chars: {promo['cta']}")
            return 1
        path = INPUT / promo["file"]
        if not path.is_file():
            print(f"[FAIL] falta imagen {path}")
            return 1

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
    print(f"[*] Graph app_id ok")
    if looks_like_phone(client_id) or client_id != app_id:
        print("[*] se actualiza whatsapp.client_id al App ID de Graph")
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
    for promo in PROMOS:
        raw = (INPUT / promo["file"]).read_bytes()
        fname = f"gonzales_{ts}_{promo['key']}.jpeg"
        print(f"[*] Meta upload {promo['key']} ({len(raw)} bytes)")
        handles[promo["key"]] = upload_header_handle(app_id, token, raw, fname, "image/jpeg")
        storage_path = f"{SCHEMA}/{fname}"
        media_urls[promo["key"]] = upload_supabase(storage_path, raw, "image/jpeg")
        print(f"    handle ok · storage {storage_path}")

    results = []
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        for promo in PROMOS:
            payload = {
                "name": promo["image_name"],
                "language": "es",
                "category": "MARKETING",
                "components": image_components(promo["image_body"], handles[promo["key"]]),
            }
            print(f"[*] create {promo['image_name']}")
            status, body = graph_post_json(f"{GRAPH}/{waba}/message_templates", token, payload)
            print(f"    HTTP {status} · {json.dumps(body, ensure_ascii=False)[:400]}")
            db_id = None
            if status in (200, 201):
                db_id = await upsert_plantilla(conn, promo["image_name"], media_urls[promo["key"]])
                print(f"    db {db_id}")
            results.append(
                {
                    "name": promo["image_name"],
                    "kind": "image",
                    "http": status,
                    "meta": body,
                    "media_url": media_urls[promo["key"]],
                    "db_id": db_id,
                    "cta": promo["cta"],
                }
            )

        carousel_payload = {
            "name": CAROUSEL_NAME,
            "language": "es",
            "category": "MARKETING",
            "components": carousel_components(handles),
        }
        print(f"[*] create {CAROUSEL_NAME}")
        status, body = graph_post_json(f"{GRAPH}/{waba}/message_templates", token, carousel_payload)
        print(f"    HTTP {status} · {json.dumps(body, ensure_ascii=False)[:400]}")
        db_id = None
        if status in (200, 201):
            db_id = await upsert_plantilla(conn, CAROUSEL_NAME, media_urls[PROMOS[0]["key"]])
            print(f"    db {db_id}")
        results.append(
            {
                "name": CAROUSEL_NAME,
                "kind": "carousel",
                "http": status,
                "meta": body,
                "media_url": media_urls[PROMOS[0]["key"]],
                "db_id": db_id,
            }
        )
    finally:
        await conn.close()

    carousel_config = [{"header_image_url": media_urls[p["key"]]} for p in PROMOS]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "plantillas-meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (OUT / "carousel_config.json").write_text(
        json.dumps(carousel_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[*] resumen {OUT / 'plantillas-meta.json'}")
    failed = [r for r in results if r["http"] not in (200, 201)]
    return 1 if failed else 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
