#!/usr/bin/env python3
"""Provisiona plantillas UTILITY de notificación Almaro (pedido/ticket/error)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")
os.chdir(BACKEND)

SCHEMA = "almaro"
TENANT_ID = "98f02431-a66f-40bf-9551-9bf66faf204d"
SECRET_NAMES = ("whatsapp.long_live_token", "whatsapp.waba")


def _merge_enabled(existing: object, extra: dict) -> dict:
    base = dict(existing) if isinstance(existing, dict) else {}
    merged = {**base, **extra, "enabled": True}
    if "subscribers" not in merged or merged["subscribers"] is None:
        merged["subscribers"] = []
    return merged


async def main() -> int:
    from core.db import close_db_pool, get_connection
    from core.tenant_secrets_crypto import decrypt_value
    from services.custom_ticket_notification_meta_template import (
        provision_custom_ticket_meta_template_on_reglas,
    )
    from services.order_notification_meta_template import (
        provision_order_notification_meta_template_on_reglas,
    )
    from services.plantillas_meta_service import sync_meta_plantillas_registry
    from services.system_error_notification_meta_template import (
        provision_system_error_meta_template_on_reglas,
    )

    token = ""
    waba = ""
    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT reglas_negocio FROM public.distribuidoras WHERE schema_name = $1",
                SCHEMA,
            )
            raw = row["reglas_negocio"]
            if isinstance(raw, str):
                reglas = json.loads(raw or "{}")
            elif isinstance(raw, dict):
                reglas = dict(raw)
            else:
                reglas = json.loads(json.dumps(raw or {}))
            reglas["order_notification"] = _merge_enabled(
                reglas.get("order_notification"),
                {"enabled": True, "strategy": "all", "subscribers": []},
            )
            reglas["custom_ia_tickets_notification"] = _merge_enabled(
                reglas.get("custom_ia_tickets_notification"),
                {"enabled": True, "strategy": "all", "subscribers": [], "message_template": ""},
            )
            reglas["system_errors_notification"] = _merge_enabled(
                reglas.get("system_errors_notification"),
                {"enabled": True, "strategy": "all", "subscribers": [], "message_template": ""},
            )
        finally:
            await conn.close()

        reglas = await provision_order_notification_meta_template_on_reglas(SCHEMA, reglas)
        reglas = await provision_custom_ticket_meta_template_on_reglas(SCHEMA, reglas)
        reglas = await provision_system_error_meta_template_on_reglas(SCHEMA, reglas)

        conn = await get_connection()
        try:
            await conn.execute(
                """
                UPDATE public.distribuidoras
                SET reglas_negocio = $1::jsonb, updated_at = now()
                WHERE schema_name = $2
                """,
                json.dumps(reglas),
                SCHEMA,
            )
            names = await conn.fetch(
                """
                SELECT template_name, category
                FROM public.meta_plantillas
                WHERE tenant_id = $1::uuid
                ORDER BY template_name
                """,
                TENANT_ID,
            )
            print("has_cross_upsell", "cross_upsell" in reglas)
            print("order meta_id:", (reglas.get("order_notification") or {}).get("meta_plantilla_id"))
            print("ticket meta_id:", (reglas.get("custom_ia_tickets_notification") or {}).get("meta_plantilla_id"))
            print("error meta_id:", (reglas.get("system_errors_notification") or {}).get("meta_plantilla_id"))
            print("subscribers: [] (vendedores GEV tienen teléfono erp-* no WhatsApp)")
            print("meta_plantillas:")
            for n in names:
                print(f"  {n['template_name']} [{n['category']}]")

            secret_rows = await conn.fetch(
                """
                SELECT name, value_enc FROM public.tenant_secrets
                WHERE tenant_id = $1::uuid AND name = ANY($2::text[])
                """,
                TENANT_ID,
                list(SECRET_NAMES),
            )
            secrets = {r["name"]: decrypt_value(str(r["value_enc"])) for r in secret_rows}
            token = secrets.get("whatsapp.long_live_token") or ""
            waba = secrets.get("whatsapp.waba") or ""
        finally:
            await conn.close()

        if token and waba:
            stats = await sync_meta_plantillas_registry(TENANT_ID, token, waba)
            print("sync_meta:", stats)
        else:
            print("[WARN] no se pudo sync WABA (credenciales)")
        return 0
    finally:
        await close_db_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
