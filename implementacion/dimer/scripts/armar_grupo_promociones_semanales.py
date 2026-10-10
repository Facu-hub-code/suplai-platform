#!/usr/bin/env python3
"""Grupo 250 para plantilla promociones_semanales + agenda puntual lunes.

Prioridad:
  1) Compraron el SKU original (no el clon Promo…) y tienen WhatsApp usable
  2) Cualquier cliente con WhatsApp usable

Schema: dimer. Pooler 6543, statement_cache_size=0.
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SCHEMA = "dimer"
TENANT_ID = "02a0c4e0-8ac7-4bf1-aee9-19b44a14f66a"
TEMPLATE_NAME = "promociones_semanales"
TEMPLATE_ID = "398055bb-abcd-42fd-b4aa-98c4a841c179"
GRUPO_NOMBRE = "Promociones semanales — lunes"
ETIQUETA_NOMBRE = "Promociones semanales"
ORIGEN = "dimer-promociones-semanales-lunes"
AGENDA_DATE = date(2026, 10, 12)
AGENDA_TIME = time(11, 0)
TARGET = 250

# SKUs originales (sin el prefijo Promo). Los clones quedan fuera a propósito.
ORIGINAL_SKUS = (
    "54165",  # Filetito pollo IQF 2x4,5
    "54164",  # Pechuga s/h s/p 2x4,5
    "5003139",  # Pollo congelado 1,9-2,1
    "5003181",  # Pollo entero Sadia
    "110A18951",  # McCain Smiles
    "158385",  # Hamburguesa vacuno Sadia
    "176139",  # Pop nuggets tempura
    "H02029000075",  # Arroz Iansa
)


def prepare() -> None:
    load_dotenv(BACKEND / ".env")
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")
    sys.path.insert(0, str(BACKEND))


async def connect() -> asyncpg.Connection:
    url = os.environ.get("SUPABASE_DB_URL_POOLER") or os.environ["SUPABASE_DB_URL"]
    return await asyncpg.connect(url.replace(":5432/", ":6543/"), statement_cache_size=0)


async def main() -> None:
    prepare()
    print("Schema: dimer (repetido). Grupo 250 promociones semanales.", flush=True)
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            WITH orig AS (
              SELECT
                pe.cliente_id,
                COUNT(*) AS lineas_orig,
                MAX(pe.fecha) AS ultima_compra_orig,
                array_agg(DISTINCT ip.product_code) AS skus_orig
              FROM dimer.items_pedido ip
              JOIN dimer.pedidos pe ON pe.id = ip.pedido_id
              WHERE pe.deleted_at IS NULL
                AND lower(COALESCE(pe.estado, '')) IN ('confirmado', 'descargado', 'enviado_erp')
                AND ip.product_code = ANY($1::text[])
              GROUP BY pe.cliente_id
            ),
            pool AS (
              SELECT
                c.id,
                c.nombre,
                c.razon_social,
                c.nombre_de_pila,
                c.phone_number,
                c.whatsapp_estado::text AS whatsapp_estado,
                c.vendedor,
                c.lifecycle,
                o.lineas_orig,
                o.ultima_compra_orig,
                o.skus_orig,
                (o.cliente_id IS NOT NULL) AS compro_original
              FROM dimer.clients c
              LEFT JOIN orig o ON o.cliente_id = c.id
              WHERE c.lifecycle = 'client'
                AND c.phone_number IS NOT NULL
                AND c.phone_number NOT LIKE '999%'
                AND length(regexp_replace(c.phone_number, '\\D', '', 'g')) >= 11
            ),
            ranked AS (
              SELECT
                p.*,
                CASE WHEN p.compro_original THEN 1 ELSE 2 END AS prioridad,
                ROW_NUMBER() OVER (
                  ORDER BY
                    CASE WHEN p.compro_original THEN 0 ELSE 1 END,
                    CASE WHEN p.whatsapp_estado = 'existente' THEN 0 ELSE 1 END,
                    p.ultima_compra_orig DESC NULLS LAST,
                    p.id
                ) AS rn
              FROM pool p
            )
            SELECT * FROM ranked WHERE rn <= $2
            ORDER BY rn
            """,
            list(ORIGINAL_SKUS),
            TARGET,
        )

        selected = [dict(r) for r in rows]
        n_orig = sum(1 for r in selected if r["compro_original"])
        n_fill = len(selected) - n_orig
        n_existente = sum(1 for r in selected if r["whatsapp_estado"] == "existente")
        print(
            f"[*] seleccionados {len(selected)} (orig={n_orig} fill={n_fill} wa_existente={n_existente})",
            flush=True,
        )
        if len(selected) < TARGET:
            print(f"[WARN] no llegamos a {TARGET}", flush=True)

        csv_path = OUT / "promociones-semanales-grupo-250.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "rn",
                    "prioridad",
                    "client_id",
                    "nombre_de_pila",
                    "razon_social",
                    "phone_number",
                    "whatsapp_estado",
                    "vendedor",
                    "compro_original",
                    "lineas_orig",
                    "ultima_compra_orig",
                    "skus_orig",
                ],
            )
            w.writeheader()
            for r in selected:
                w.writerow(
                    {
                        "rn": r["rn"],
                        "prioridad": r["prioridad"],
                        "client_id": r["id"],
                        "nombre_de_pila": r.get("nombre_de_pila") or "",
                        "razon_social": r.get("razon_social") or "",
                        "phone_number": r.get("phone_number") or "",
                        "whatsapp_estado": r.get("whatsapp_estado") or "",
                        "vendedor": r.get("vendedor") or "",
                        "compro_original": r["compro_original"],
                        "lineas_orig": r.get("lineas_orig") or 0,
                        "ultima_compra_orig": r["ultima_compra_orig"] or "",
                        "skus_orig": "|".join(r["skus_orig"] or []),
                    }
                )
        print(f"[*] csv {csv_path}", flush=True)

        etq_id = await conn.fetchval(
            "SELECT id FROM dimer.etiquetas WHERE name = $1", ETIQUETA_NOMBRE
        )
        if etq_id:
            etq_id = int(etq_id)
        else:
            etq_id = int(
                await conn.fetchval(
                    "INSERT INTO dimer.etiquetas (name) VALUES ($1) RETURNING id",
                    ETIQUETA_NOMBRE,
                )
            )
        print(f"[*] etiqueta {etq_id} {ETIQUETA_NOMBRE}", flush=True)

        client_ids = [int(r["id"]) for r in selected]
        existing = await conn.fetchrow(
            "SELECT id FROM dimer.grupos WHERE nombre = $1", GRUPO_NOMBRE
        )
        if existing:
            gid = int(existing["id"])
            await conn.execute(
                """
                UPDATE dimer.grupos
                SET activo_ai = true,
                    etiqueta_ids = ARRAY[$2]::int[],
                    client_ids = $3::int[],
                    vendedor_id = NULL,
                    dias_visita = NULL
                WHERE id = $1
                """,
                gid,
                etq_id,
                client_ids,
            )
            print(f"[*] update grupo {gid}", flush=True)
        else:
            gid = int(
                await conn.fetchval(
                    """
                    INSERT INTO dimer.grupos
                        (nombre, activo_ai, etiqueta_ids, client_ids)
                    VALUES ($1, true, ARRAY[$2]::int[], $3::int[])
                    RETURNING id
                    """,
                    GRUPO_NOMBRE,
                    etq_id,
                    client_ids,
                )
            )
            print(f"[*] insert grupo {gid}", flush=True)

        await conn.execute(
            """
            INSERT INTO dimer.clientes_etiquetas (client_id, etiqueta_id)
            SELECT x, $1 FROM unnest($2::int[]) AS x
            ON CONFLICT DO NOTHING
            """,
            etq_id,
            client_ids,
        )

        tagged = await conn.fetchval(
            "SELECT COUNT(*) FROM dimer.clientes_etiquetas WHERE etiqueta_id = $1",
            etq_id,
        )
        verify = await conn.fetchrow(
            """
            SELECT id, nombre, cardinality(client_ids) AS n
            FROM dimer.grupos WHERE id = $1
            """,
            gid,
        )

        agenda = await conn.fetchrow(
            """
            INSERT INTO dimer.agenda (
                grupo_id, meta_plantilla_id, tipo, hora_envio,
                fecha_programada, dynamic_params, activo, origen
            )
            SELECT
                $1::int,
                $2::uuid,
                'puntual',
                $3::time,
                $4::date,
                '[]'::jsonb,
                true,
                $5
            WHERE NOT EXISTS (
                SELECT 1 FROM dimer.agenda a
                WHERE a.grupo_id = $1
                  AND a.meta_plantilla_id = $2::uuid
                  AND a.tipo = 'puntual'
                  AND a.fecha_programada = $4::date
            )
            RETURNING id, hora_envio::text, fecha_programada, activo, origen
            """,
            gid,
            TEMPLATE_ID,
            AGENDA_TIME,
            AGENDA_DATE,
            ORIGEN,
        )
        if not agenda:
            agenda = await conn.fetchrow(
                """
                SELECT id, hora_envio::text, fecha_programada, activo, origen, enviado_at
                FROM dimer.agenda
                WHERE grupo_id = $1
                  AND meta_plantilla_id = $2::uuid
                  AND fecha_programada = $3::date
                """,
                gid,
                TEMPLATE_ID,
                AGENDA_DATE,
            )
            agenda_info = {"created": False, **dict(agenda)} if agenda else {"created": False}
        else:
            agenda_info = {"created": True, **dict(agenda)}

        summary = {
            "at": datetime.now(timezone.utc).isoformat(),
            "schema": SCHEMA,
            "skus_originales": list(ORIGINAL_SKUS),
            "target": TARGET,
            "seleccionados": len(selected),
            "prioridad_1_originales": n_orig,
            "prioridad_2_fill": n_fill,
            "whatsapp_existente": n_existente,
            "etiqueta_id": etq_id,
            "etiqueta": ETIQUETA_NOMBRE,
            "etiquetados": int(tagged),
            "grupo_id": gid,
            "grupo": GRUPO_NOMBRE,
            "grupo_n": int(verify["n"]) if verify else None,
            "plantilla": TEMPLATE_NAME,
            "plantilla_id": TEMPLATE_ID,
            "agenda": {
                **{k: (str(v) if isinstance(v, date) else v) for k, v in agenda_info.items()}
            },
            "csv": str(csv_path.relative_to(ROOT)),
        }
        out_json = OUT / "promociones-semanales-grupo.json"
        out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str), flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
