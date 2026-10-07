#!/usr/bin/env python3
"""Congelados: sync día de visita desde Odoo + grupos de envío ≤200.

- Odoo res.partner tiene booleanos lunes..domingo (y user_id = ruta, no persona).
- Actualiza dimer.clients.dia_de_visita.
- Crea grupos explícitos (client_ids) de a lo sumo 200 por día.

Uso:
  set -a && source ../../../backend-supabase/.env && set +a
  python implementacion/dimer/scripts/armar_grupos_congelados_por_dia.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SCHEMA = "dimer"
ETIQUETA_CONGELADOS = 25
CHUNK = 200

DAY_BOOL = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
DAY_LABEL = {
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
    "domingo": "Domingo",
}
ROUTES = [
    "20 - HORECA",
    "13 - Congelados Interior",
    "2 - Valparaiso C",
    "8 - Santa Ines/Villa Hermosa",
    "34 - Quillota / La Calera",
    "35 - Recreo/Forestal",
    "19 - Tabolango - Papudo",
    "17 - Limache/Olmue",
    "18 - Los Andes/San Felipe",
    "16 - Especializado Litoral",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def prepare_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")
    sys.path.insert(0, str(BACKEND))


def norm_rut(s: object) -> str:
    return str(s or "").strip().upper().replace(".", "").replace(" ", "")


def rut_keys(s: object) -> set[str]:
    s = norm_rut(s)
    if not s:
        return set()
    keys = {s, s.replace("-", "")}
    if "-" not in s and len(s) >= 2:
        keys.add(s[:-1] + "-" + s[-1])
    return keys


def chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield i // n + 1, items[i : i + n]


async def fetch_odoo_visitas(client_ruts: dict[int, set[str]]) -> list[dict]:
    from erp.services.erp_sync_service import get_connector_for_schema

    c = await get_connector_for_schema(SCHEMA)
    read_fields = ["id", "name", "vat", "user_id", "route_id", "phone", "email", "secuencia"] + DAY_BOOL

    log("[*] Odoo: partners con día de visita…")
    domain = ["|"] * (len(DAY_BOOL) - 1) + [[d, "=", True] for d in DAY_BOOL]
    partners_days = await c._search_read_all("res.partner", domain, read_fields)
    log(f"    con flags de día: {len(partners_days)}")

    users = await c._execute_kw(
        "res.users",
        "search_read",
        [[["name", "in", ROUTES]]],
        {"fields": ["id", "name"]},
    )
    uids = [u["id"] for u in users]
    partners_user = await c._search_read_all("res.partner", [["user_id", "in", uids]], read_fields)
    log(f"    con user de ruta Congelados: {len(partners_user)}")

    by_vat: dict[str, tuple[int, dict]] = {}

    def score(p: dict) -> int:
        return (
            (10 if any(p.get(d) for d in DAY_BOOL) else 0)
            + (5 if p.get("user_id") else 0)
            + (1 if p.get("phone") else 0)
        )

    def index(p: dict) -> None:
        sc = score(p)
        for k in rut_keys(p.get("vat")):
            prev = by_vat.get(k)
            if not prev or sc > prev[0]:
                by_vat[k] = (sc, p)

    for p in partners_days:
        index(p)
    for p in partners_user:
        index(p)

    resolved = []
    for cid, ruts in client_ruts.items():
        hit = None
        for rut in ruts:
            for k in rut_keys(rut):
                if k in by_vat:
                    hit = by_vat[k][1]
                    break
            if hit:
                break
        if not hit:
            resolved.append(
                {
                    "client_id": cid,
                    "partner_id": None,
                    "primary_dia": None,
                    "dias": [],
                    "user": None,
                    "odoo_user_id": None,
                    "secuencia": "",
                }
            )
            continue
        days = [d for d in DAY_BOOL if hit.get(d)]
        user = hit.get("user_id")
        uname = user[1] if isinstance(user, (list, tuple)) else None
        uid = int(user[0]) if isinstance(user, (list, tuple)) else None
        resolved.append(
            {
                "client_id": cid,
                "partner_id": hit["id"],
                "primary_dia": days[0] if days else None,
                "dias": days,
                "user": uname,
                "odoo_user_id": uid,
                "secuencia": str(hit.get("secuencia") or ""),
                "phone_odoo": hit.get("phone") or "",
            }
        )
    return resolved


async def main() -> None:
    prepare_env()
    import asyncpg

    match = list(csv.DictReader((OUT / "congelados-match-ok.csv").open(encoding="utf-8")))
    excel = list(csv.DictReader((OUT / "congelados-excel.csv").open(encoding="utf-8")))
    excel_by_odoo = {r["odoo_id"]: r for r in excel}

    client_ruts: dict[int, set[str]] = defaultdict(set)
    for r in match:
        cid = int(r["client_id"])
        if r.get("cuit"):
            client_ruts[cid].add(norm_rut(r["cuit"]))
        er = excel_by_odoo.get(r.get("odoo_id_excel") or "")
        if er:
            client_ruts[cid].add(er["rut_norm"])

    resolved = await fetch_odoo_visitas(client_ruts)
    with_day = [r for r in resolved if r.get("primary_dia")]
    log(
        f"[*] Resueltos {len(resolved)} | con día {len(with_day)} | "
        f"sin día {len(resolved)-len(with_day)}"
    )
    log(f"    distribución: {Counter(r['primary_dia'] for r in with_day)}")
    personish = sum(
        1
        for r in resolved
        if r.get("user")
        and not re.match(r"^\d+\s*-", r["user"])
        and r["user"] not in {"Clientes Inactivos", "Empleados"}
    )
    log(f"    user_id con nombre de persona (no ruta): {personish}")

    with (OUT / "congelados-odoo-visitas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "client_id",
                "partner_id",
                "primary_dia",
                "dias",
                "user",
                "odoo_user_id",
                "secuencia",
                "phone_odoo",
            ],
        )
        w.writeheader()
        for r in resolved:
            w.writerow(
                {
                    "client_id": r["client_id"],
                    "partner_id": r.get("partner_id") or "",
                    "primary_dia": r.get("primary_dia") or "",
                    "dias": "|".join(r.get("dias") or []),
                    "user": r.get("user") or "",
                    "odoo_user_id": r.get("odoo_user_id") or "",
                    "secuencia": r.get("secuencia") or "",
                    "phone_odoo": r.get("phone_odoo") or "",
                }
            )

    url = (os.environ.get("SUPABASE_DB_URL_POOLER") or os.environ["SUPABASE_DB_URL"]).replace(
        ":5432/", ":6543/"
    )
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        # 1) Update dia_de_visita in batches
        log("[*] Actualizando dia_de_visita en clients…")
        ids = [r["client_id"] for r in with_day]
        dias = [r["primary_dia"] for r in with_day]
        # Cast via text to enum (handles accented variants if DB requires)
        updated = await conn.fetch(
            """
            WITH data AS (
              SELECT * FROM unnest($1::int[], $2::text[]) AS t(id, dia)
            ),
            upd AS (
              UPDATE dimer.clients c
              SET dia_de_visita = d.dia::core.dia_de_visita_enum,
                  updated_at = now()
              FROM data d
              WHERE c.id = d.id
              RETURNING c.id, c.dia_de_visita::text AS dia
            )
            SELECT dia, COUNT(*)::int AS n FROM upd GROUP BY 1 ORDER BY 1
            """,
            ids,
            dias,
        )
        log(f"    updated by day: { {r['dia']: r['n'] for r in updated} }")

        # 2) Build chunks per day (stable: secuencia then client_id)
        by_day: dict[str, list[dict]] = defaultdict(list)
        for r in with_day:
            by_day[r["primary_dia"]].append(r)
        for dia, rows in by_day.items():
            rows.sort(key=lambda x: (x.get("secuencia") or "9999", x["client_id"]))

        # Remove previous Congelados envío groups (name prefix) to be idempotent
        old = await conn.fetch(
            """
            SELECT id, nombre FROM dimer.grupos
            WHERE nombre LIKE 'Congelados - %'
               OR nombre ~ '^Congelados (Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)'
            """
        )
        if old:
            await conn.execute(
                "DELETE FROM dimer.grupos WHERE id = ANY($1::int[])",
                [r["id"] for r in old],
            )
            log(f"    borrados grupos viejos: {len(old)}")

        # Keep umbrella grupo Congelados (id 20) as etiqueta-based
        await conn.execute(
            """
            UPDATE dimer.grupos
            SET etiqueta_ids = ARRAY[$1]::int[],
                client_ids = NULL,
                dias_visita = NULL,
                activo_ai = true
            WHERE id = 20
            """,
            ETIQUETA_CONGELADOS,
        )

        created = []
        for dia in DAY_BOOL:
            rows = by_day.get(dia) or []
            if not rows:
                continue
            label = DAY_LABEL[dia]
            total_parts = (len(rows) + CHUNK - 1) // CHUNK
            for part, chunk_rows in chunks(rows, CHUNK):
                cids = [r["client_id"] for r in chunk_rows]
                nombre = f"Congelados - {label} {part}/{total_parts}"
                if total_parts == 1:
                    nombre = f"Congelados - {label}"
                gid = await conn.fetchval(
                    """
                    INSERT INTO dimer.grupos
                        (nombre, activo_ai, etiqueta_ids, dias_visita, client_ids, vendedor_id)
                    VALUES (
                        $1, true, ARRAY[$2]::int[],
                        ARRAY[$3]::core.dia_de_visita_enum[],
                        $4::int[], NULL
                    )
                    RETURNING id
                    """,
                    nombre,
                    ETIQUETA_CONGELADOS,
                    dia,
                    cids,
                )
                created.append(
                    {
                        "grupo_id": int(gid),
                        "nombre": nombre,
                        "dia": dia,
                        "part": part,
                        "total_parts": total_parts,
                        "clientes": len(cids),
                    }
                )
                log(f"    grupo {gid}: {nombre} ({len(cids)})")

        with (OUT / "congelados-grupos-envio.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["grupo_id", "nombre", "dia", "part", "total_parts", "clientes"],
            )
            w.writeheader()
            for row in created:
                w.writerow(row)

        # membership verify via client_ids length
        ver = await conn.fetch(
            """
            SELECT id, nombre,
                   cardinality(client_ids) AS n,
                   dias_visita::text AS dias
            FROM dimer.grupos
            WHERE nombre LIKE 'Congelados - %'
            ORDER BY nombre
            """
        )
        summary = {
            "at": datetime.now(timezone.utc).isoformat(),
            "clients_with_day": len(with_day),
            "day_dist": dict(Counter(r["primary_dia"] for r in with_day)),
            "grupos": created,
            "verify": [dict(r) for r in ver],
            "vendedor_api": {
                "campo": "res.partner.user_id (Salesperson)",
                "tiene_nombre_persona": False,
                "nota": (
                    "En Odoo el salesperson es la cuenta de ruta "
                    "('13 - Congelados Interior'), no el nombre de pila. "
                    "No hay otro campo de vendedor persona en res.partner."
                ),
            },
            "visita_api": {
                "campos": DAY_BOOL,
                "cobertura": f"{len(with_day)}/{len(resolved)}",
            },
        }
        (OUT / "congelados-grupos-envio.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        log("[✓] Listo")
        log(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
