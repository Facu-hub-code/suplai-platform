#!/usr/bin/env python3
"""Explore Odoo partner fields for salesperson person name + visit day."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"


def prepare():
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")
    sys.path.insert(0, str(BACKEND))


async def main():
    prepare()
    from erp.services.erp_sync_service import get_connector_for_schema

    c = await get_connector_for_schema("dimer")
    fields = await c._execute_kw(
        "res.partner",
        "fields_get",
        [],
        {"attributes": ["string", "type", "relation", "help", "selection"]},
    )
    interesting = []
    for k, v in fields.items():
        blob = f"{k} {v.get('string','')} {v.get('help','')}".lower()
        if any(
            x in blob
            for x in (
                "visit",
                "visita",
                "día",
                "dia ",
                "dias",
                "week",
                "lunes",
                "martes",
                "user",
                "vend",
                "sales",
                "ruta",
                "route",
                "ipr",
                "comercial",
                "seller",
                "agenda",
                "frecuencia",
            )
        ):
            interesting.append((k, v))

    print("=== interesting partner fields ===")
    for k, v in sorted(interesting, key=lambda x: x[0]):
        sel = v.get("selection")
        print(
            f"  {k}: type={v.get('type')} string={v.get('string')!r} "
            f"rel={v.get('relation')} sel={sel[:8] if sel else None}"
        )

    # Candidate field names to read on sample partners
    cand = [
        k
        for k, _ in interesting
        if fields[k]["type"]
        in ("char", "text", "many2one", "selection", "boolean", "integer", "many2many", "one2many", "date", "float")
    ]
    # Always include basics
    base = ["id", "name", "vat", "user_id", "route_id", "phone", "email", "comment", "function"]
    read_fields = sorted(set(base + cand))
    # Cap if huge
    if len(read_fields) > 80:
        # prioritize visit/user/route
        pri = [k for k in read_fields if any(x in k.lower() for x in ("visit", "dia", "day", "user", "route", "vend", "sales", "ipr", "week"))]
        read_fields = sorted(set(base + pri))[:80]

    print(f"\nReading sample with {len(read_fields)} fields…")
    samples = await c._execute_kw(
        "res.partner",
        "search_read",
        [[["customer_rank", ">", 0], ["user_id", "!=", False]]],
        {"fields": read_fields, "limit": 8, "order": "id desc"},
    )
    for p in samples:
        slim = {k: p.get(k) for k in read_fields if p.get(k) not in (False, None, "", [], {})}
        print("\n---", p.get("id"), p.get("name"))
        print(json.dumps(slim, ensure_ascii=False, default=str)[:1200])

    # Also inspect ipr.route for visit days (monday..sunday booleans we saw)
    rf = await c._execute_kw(
        "ipr.route",
        "fields_get",
        [],
        {"attributes": ["string", "type", "relation"]},
    )
    print("\n=== ipr.route day-ish fields ===")
    for k, v in sorted(rf.items()):
        if any(x in k.lower() or x in str(v.get("string", "")).lower() for x in ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "dia", "visit", "user", "vend")):
            print(f"  {k}: {v.get('type')} {v.get('string')}")

    routes = await c._search_read_all(
        "ipr.route",
        [],
        ["id", "name", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "activity_user_id"],
    )
    print(f"\nipr.routes with days: {len(routes)}")
    day_counts = Counter()
    for r in routes:
        days = [d for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday") if r.get(d)]
        day_counts[",".join(days) or "(none)"] += 1
        if r.get("name") in ("Chorrillos", "Peñablanca", "Valparaiso", "Litoral", "QuillotaCale", "Recreo", "Limache"):
            print(" ", r.get("id"), r.get("name"), "days", days, "activity_user", r.get("activity_user_id"))

    print("day combo distribution:", day_counts.most_common(15))

    # Check if there's a dedicated visit day model
    for model in ("ipr.visit", "ipr.partner.visit", "visit.day", "crm.lead"):
        try:
            n = await c._execute_kw(model, "search_count", [[]])
            print(f"model {model} exists count={n}")
        except Exception as e:
            print(f"model {model}: {e}")

    (OUT / "congelados-odoo-partner-fields.json").write_text(
        json.dumps(
            {
                "interesting": {
                    k: {
                        "string": v.get("string"),
                        "type": v.get("type"),
                        "relation": v.get("relation"),
                        "selection": v.get("selection"),
                    }
                    for k, v in interesting
                },
                "sample": samples,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    print("\nwrote fields dump")


if __name__ == "__main__":
    asyncio.run(main())
