#!/usr/bin/env python3
"""Manda los casos de casos-reales/ al webhook de prod desde el cliente mock y guarda respuestas + búsquedas."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = ROOT / "implementacion/almaro"
CASES_DIR = TENANT_DIR / "casos-reales/casos"
SCHEMA = "almaro"
MOCK_PHONE = "549358509867"
WEBHOOK = "https://agente-conversacional-multitenant-production.up.railway.app/webhook"
BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def reset_context(conn: asyncpg.Connection) -> None:
    conv_id = await conn.fetchval(
        """
        SELECT c.id FROM core.conversations c
        JOIN public.distribuidoras d ON d.id = c.tenant_id
        WHERE d.schema_name = $1 AND c.session_id = $2
        ORDER BY c.id DESC LIMIT 1
        """,
        SCHEMA,
        MOCK_PHONE,
    )
    if conv_id:
        requests.delete(f"{BACKEND}/{SCHEMA}/conversaciones/{conv_id}/context", timeout=30)


async def searches_since(conn: asyncpg.Connection, since: datetime) -> list[list[str]]:
    rows = await conn.fetch(
        """
        SELECT e.event_payload FROM core.conversation_events e
        JOIN core.conversations c ON c.id = e.conversation_id
        JOIN public.distribuidoras d ON d.id = c.tenant_id
        WHERE d.schema_name = $1 AND c.session_id = $2
          AND e.event_type = 'catalog_search_snapshot' AND e.created_at >= $3
        ORDER BY e.created_at
        """,
        SCHEMA,
        MOCK_PHONE,
        since,
    )
    out = []
    for r in rows:
        payload = r["event_payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        out.append([f"{i.get('product_code')} {i.get('nombre')}" for i in (payload.get("items") or [])[:5]])
    return out


async def main() -> int:
    load_dotenv(ROOT.parent / "backend-supabase/.env")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    only = set(sys.argv[1:])
    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        agent_phone = str(int(float(await conn.fetchval(
            "SELECT agent_phone_number FROM public.distribuidoras WHERE schema_name = $1", SCHEMA
        ))))
        results = []
        for case_dir in sorted(p for p in CASES_DIR.iterdir() if (p / "caso.json").is_file()):
            if only and case_dir.name not in only:
                continue
            spec = json.loads((case_dir / "caso.json").read_text(encoding="utf-8"))
            await reset_context(conn)
            since = datetime.now(timezone.utc)
            t0 = time.perf_counter()
            resp = requests.post(
                WEBHOOK,
                json={
                    "provider": "custom",
                    "to_agent_phone": agent_phone,
                    "from_user_id": MOCK_PHONE,
                    "text": spec["message"],
                    "timestamp": int(time.time()),
                    "provider_message_id": str(uuid.uuid4()),
                },
                timeout=180,
            )
            elapsed = round(time.perf_counter() - t0, 1)
            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text}
            await asyncio.sleep(2)
            results.append({
                "caso": case_dir.name,
                "mensaje": spec["message"],
                "esperado": spec["expected_behavior"],
                "status": resp.status_code,
                "segundos": elapsed,
                "respuesta": data,
                "busquedas": await searches_since(conn, since),
            })
            print(f"[{case_dir.name}] {resp.status_code} {elapsed}s")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = TENANT_DIR / f"outputs/prueba-marcas-competencia-{stamp}.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"OK {out.relative_to(ROOT)}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
