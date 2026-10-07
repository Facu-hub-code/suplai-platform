#!/usr/bin/env python3
"""Sync vendedores de rutas Congelados desde Odoo → dimer + asignación por Excel.

Odoo guarda el salesperson como ruta (ej. "13 - Congelados Interior"), no el
nombre de pila. Este script:
  1) Lee res.users de esas rutas
  2) Upsert en dimer.vendedores (codigo_ruta + telefono placeholder si falta)
  3) Asigna clientes Congelados en lote según columna Vendedor del Excel
  4) Escribe clients.vendedor con el nombre disponible (ruta u persona conocida)

Uso:
  set -a && source ../../../backend-supabase/.env && set +a
  python implementacion/dimer/scripts/sync_vendedores_congelados_odoo.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SCHEMA = "dimer"
ETIQUETA_CONGELADOS = 25

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

KNOWN_PERSON = {
    "9 - Casablanca/Algarrobo": ("Gustavo López", "56964037193"),
    "28 - El Tabo / Cartagena": ("Doralisa Vivencio", "56979888434"),
    "29 - San Antonio Sur / Sto. Domingo": ("Maryvonne Zárate", "56964636942"),
    "30 - Melipilla": ("María Verónica Montes", "56958142220"),
    "31 - Curacavi/Maria Pinto": ("Luis Torrealba", "56958146252"),
    "32 - El Quisco / Isla Negra": ("José Quero", "56961816090"),
    "33 - San Antonio Norte": ("Natalia Martinez", "56958141749"),
}


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


def codigo_from_ruta(ruta: str) -> str:
    m = re.match(r"^(\d+)\s*-", ruta.strip())
    return m.group(1) if m else ruta


def zona_from_ruta(ruta: str) -> str:
    parts = ruta.split(" - ", 1)
    return parts[1].strip() if len(parts) == 2 else ruta


def email_hint(email: str) -> str:
    email = (email or "").strip()
    if not email or "@" not in email or email in {".", "False"}:
        return ""
    local = email.split("@", 1)[0]
    if local.startswith("dimer."):
        return local[len("dimer.") :]
    return ""


def norm_phone(phone: object) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("56") and len(digits) >= 11:
        return digits
    if digits.startswith("9") and len(digits) == 9:
        return "56" + digits
    return digits


async def fetch_odoo_routes() -> list[dict]:
    from erp.services.erp_sync_service import get_connector_for_schema

    connector = await get_connector_for_schema(SCHEMA)
    if not connector:
        raise RuntimeError("Sin conector Odoo para dimer")
    users = await connector._execute_kw(
        "res.users",
        "search_read",
        [[["name", "in", ROUTES]]],
        {"fields": ["id", "name", "login", "active", "partner_id", "phone", "mobile", "email"]},
    )
    out = []
    for u in users:
        email = (u.get("email") or "").strip()
        phone = norm_phone(u.get("phone") or u.get("mobile"))
        pid = u["partner_id"][0] if isinstance(u.get("partner_id"), (list, tuple)) else None
        if pid:
            prow = await connector._execute_kw(
                "res.partner",
                "read",
                [[pid]],
                {"fields": ["email", "phone", "mobile"]},
            )
            p = prow[0] if prow else {}
            if not email or email in {".", "False"}:
                email = (p.get("email") or "").strip()
            if not phone:
                phone = norm_phone(p.get("phone") or p.get("mobile"))
        known = KNOWN_PERSON.get(u["name"])
        codigo = codigo_from_ruta(u["name"])
        out.append(
            {
                "odoo_user_id": int(u["id"]),
                "ruta": u["name"],
                "codigo_ruta": codigo,
                "zona": zona_from_ruta(u["name"]),
                "login": u.get("login"),
                "email": email if email not in {".", "False"} else "",
                "telefono": (known[1] if known else "") or phone or f"5690000{codigo.zfill(4)[-4:]}",
                "telefono_placeholder": not bool((known[1] if known else "") or phone),
                "email_hint": email_hint(email),
                "nombre_persona": known[0] if known else None,
            }
        )
    return out


async def main() -> None:
    prepare_env()
    import asyncpg

    log("[*] Fetch Odoo route users…")
    odoo_routes = await fetch_odoo_routes()
    log(f"    {len(odoo_routes)} rutas")
    for r in odoo_routes:
        log(
            f"    {r['codigo_ruta']:>3} {r['ruta']} | "
            f"email={r['email'] or '-'} | hint={r['email_hint'] or '-'} | "
            f"tel={'PLACEHOLDER' if r['telefono_placeholder'] else r['telefono']}"
        )

    match_rows = list(csv.DictReader((OUT / "congelados-match-ok.csv").open(encoding="utf-8")))
    client_route: dict[int, str] = {}
    for row in match_rows:
        client_route[int(row["client_id"])] = row["vendedor_excel"]
    log(f"[*] Clientes a asignar: {len(client_route)}")

    url = (os.environ.get("SUPABASE_DB_URL_POOLER") or os.environ["SUPABASE_DB_URL"]).replace(
        ":5432/", ":6543/"
    )
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        vend_by_ruta: dict[str, int] = {}
        rows_out = []

        log("[*] Upsert vendedores…")
        for r in odoo_routes:
            nombre = r["nombre_persona"] or r["ruta"]
            existing = await conn.fetchrow(
                """
                SELECT id, nombre, telefono FROM dimer.vendedores
                WHERE codigo_ruta = $1 OR nombre = $2
                ORDER BY id LIMIT 1
                """,
                r["codigo_ruta"],
                r["ruta"],
            )
            if existing:
                keep_person = r["nombre_persona"] or (
                    existing["nombre"]
                    and not re.match(r"^\d+\s*-", str(existing["nombre"]))
                    and existing["nombre"] not in ROUTES
                )
                new_nombre = r["nombre_persona"] or (existing["nombre"] if keep_person else r["ruta"])
                new_tel = (
                    existing["telefono"]
                    if r["telefono_placeholder"] and existing["telefono"]
                    else r["telefono"]
                )
                await conn.execute(
                    """
                    UPDATE dimer.vendedores
                    SET nombre=$2, telefono=$3, zona=$4, codigo_ruta=$5, activo=true, updated_at=now()
                    WHERE id=$1
                    """,
                    existing["id"],
                    new_nombre,
                    new_tel,
                    r["zona"],
                    r["codigo_ruta"],
                )
                vid = int(existing["id"])
                log(f"    update id={vid} {new_nombre}")
            else:
                vid = int(
                    await conn.fetchval(
                        """
                        INSERT INTO dimer.vendedores
                            (nombre, telefono, zona, codigo_ruta, activo, is_mock)
                        VALUES ($1,$2,$3,$4,true,false)
                        RETURNING id
                        """,
                        nombre,
                        r["telefono"],
                        r["zona"],
                        r["codigo_ruta"],
                    )
                )
                new_nombre = nombre
                log(f"    insert id={vid} {nombre}")

            vend_by_ruta[r["ruta"]] = vid
            rows_out.append({**r, "vendedor_id": vid, "nombre_en_suplai": new_nombre})

        # Build assignment arrays
        client_ids: list[int] = []
        vendedor_ids: list[int] = []
        displays: list[str] = []
        rutas: list[str] = []
        odoo_uids: list[int] = []
        es_ruta_flags: list[bool] = []
        meta_by_vid = {r["vendedor_id"]: r for r in rows_out}

        for cid, ruta in client_route.items():
            vid = vend_by_ruta.get(ruta)
            if not vid:
                continue
            meta = meta_by_vid[vid]
            display = meta.get("nombre_persona") or meta["nombre_en_suplai"]
            client_ids.append(cid)
            vendedor_ids.append(vid)
            displays.append(display)
            rutas.append(ruta)
            odoo_uids.append(int(meta["odoo_user_id"]))
            es_ruta_flags.append(meta.get("nombre_persona") is None)

        log(f"[*] Asignando {len(client_ids)} clientes en lote…")

        # Deactivate other VC links for these clients
        await conn.execute(
            """
            UPDATE dimer.vendedores_clientes vc
            SET activo = false, updated_at = now()
            FROM unnest($1::int[], $2::int[]) AS x(client_id, vendedor_id)
            WHERE vc.cliente_id = x.client_id
              AND vc.vendedor_id <> x.vendedor_id
              AND COALESCE(vc.activo, true)
            """,
            client_ids,
            vendedor_ids,
        )

        # Upsert active VC
        await conn.execute(
            """
            INSERT INTO dimer.vendedores_clientes (vendedor_id, cliente_id, activo)
            SELECT v, c, true
            FROM unnest($1::int[], $2::int[]) AS x(v, c)
            ON CONFLICT (vendedor_id, cliente_id)
            DO UPDATE SET activo = true, updated_at = now()
            """,
            vendedor_ids,
            client_ids,
        )

        # Update clients.vendedor + metadata
        # Preserve existing personal Litoral names on route 16 when already set
        updated = await conn.fetch(
            """
            WITH data AS (
              SELECT *
              FROM unnest(
                $1::int[], $2::text[], $3::text[], $4::int[], $5::bool[], $6::int[]
              ) AS t(client_id, display, ruta, odoo_uid, es_ruta, vendedor_id)
            ),
            upd AS (
              UPDATE dimer.clients c
              SET vendedor = CASE
                    WHEN d.ruta = '16 - Especializado Litoral'
                     AND c.vendedor IS NOT NULL
                     AND btrim(c.vendedor) <> ''
                     AND c.vendedor !~ '^\\d+\\s*-'
                    THEN c.vendedor
                    ELSE d.display
                  END,
                  metadata = COALESCE(c.metadata, '{}'::jsonb) || jsonb_build_object(
                    'congelados_ruta_odoo', d.ruta,
                    'congelados_odoo_user_id', d.odoo_uid,
                    'congelados_vendedor_id', d.vendedor_id,
                    'congelados_nombre_es_ruta',
                      CASE
                        WHEN d.ruta = '16 - Especializado Litoral'
                         AND c.vendedor IS NOT NULL
                         AND btrim(c.vendedor) <> ''
                         AND c.vendedor !~ '^\\d+\\s*-'
                        THEN false
                        ELSE d.es_ruta
                      END
                  ),
                  updated_at = now()
              FROM data d
              WHERE c.id = d.client_id
              RETURNING c.id,
                        c.vendedor,
                        (c.metadata->>'congelados_nombre_es_ruta')::boolean AS nombre_es_ruta,
                        c.metadata->>'congelados_ruta_odoo' AS ruta
            )
            SELECT * FROM upd
            """
            ,
            client_ids,
            displays,
            rutas,
            odoo_uids,
            es_ruta_flags,
            vendedor_ids,
        )
        log(f"    clients actualizados: {len(updated)}")

        ruta_stats: dict[str, Counter] = {r["ruta"]: Counter() for r in rows_out}
        for u in updated:
            ruta = u["ruta"] or ""
            ruta_stats.setdefault(ruta, Counter())["asignados"] += 1
            if u["nombre_es_ruta"]:
                ruta_stats[ruta]["pendiente_nombre_persona"] += 1
            else:
                ruta_stats[ruta]["con_nombre_persona"] += 1

        with (OUT / "congelados-vendedores-odoo.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "vendedor_id",
                    "codigo_ruta",
                    "ruta_odoo",
                    "nombre_en_suplai",
                    "nombre_es_ruta",
                    "email",
                    "email_hint",
                    "telefono",
                    "telefono_placeholder",
                    "odoo_user_id",
                    "clientes_asignados",
                    "pendiente_nombre_persona",
                ],
            )
            w.writeheader()
            for r in rows_out:
                st = ruta_stats.get(r["ruta"], Counter())
                w.writerow(
                    {
                        "vendedor_id": r["vendedor_id"],
                        "codigo_ruta": r["codigo_ruta"],
                        "ruta_odoo": r["ruta"],
                        "nombre_en_suplai": r["nombre_en_suplai"],
                        "nombre_es_ruta": r["nombre_persona"] is None,
                        "email": r["email"],
                        "email_hint": r["email_hint"],
                        "telefono": r["telefono"],
                        "telefono_placeholder": r["telefono_placeholder"],
                        "odoo_user_id": r["odoo_user_id"],
                        "clientes_asignados": st.get("asignados", 0),
                        "pendiente_nombre_persona": st.get("pendiente_nombre_persona", 0),
                    }
                )

        ver = await conn.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM dimer.clientes_etiquetas WHERE etiqueta_id=$1) AS etiquetados,
              (SELECT COUNT(DISTINCT c.id)
                 FROM dimer.clients c
                 JOIN dimer.vendedores_clientes vc ON vc.cliente_id=c.id AND COALESCE(vc.activo,true)
                 JOIN dimer.clientes_etiquetas ce ON ce.client_id=c.id AND ce.etiqueta_id=$1
              ) AS con_vc,
              (SELECT COUNT(*)
                 FROM dimer.clients c
                 JOIN dimer.clientes_etiquetas ce ON ce.client_id=c.id AND ce.etiqueta_id=$1
                WHERE COALESCE(c.metadata->>'congelados_nombre_es_ruta','false')='true'
              ) AS nombre_es_ruta,
              (SELECT COUNT(*)
                 FROM dimer.clients c
                 JOIN dimer.clientes_etiquetas ce ON ce.client_id=c.id AND ce.etiqueta_id=$1
                WHERE c.vendedor IS NOT NULL AND btrim(c.vendedor)<>''
                  AND COALESCE(c.metadata->>'congelados_nombre_es_ruta','true')='false'
              ) AS con_nombre_persona
            """,
            ETIQUETA_CONGELADOS,
        )

        summary = {
            "at": datetime.now(timezone.utc).isoformat(),
            "rutas_odoo": len(odoo_routes),
            "asignados": len(updated),
            "verify": dict(ver),
            "nota": (
                "Odoo no tiene nombre de pila: el salesperson es la ruta. "
                "Completar nombre+teléfono real en congelados-vendedores-odoo.csv "
                "antes de enviar plantilla Meta."
            ),
            "by_ruta": {k: dict(v) for k, v in ruta_stats.items()},
            "email_hints": {
                r["ruta"]: r["email_hint"] for r in rows_out if r.get("email_hint")
            },
        }
        (OUT / "congelados-vendedores-sync.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        log("[✓] Listo")
        log(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
