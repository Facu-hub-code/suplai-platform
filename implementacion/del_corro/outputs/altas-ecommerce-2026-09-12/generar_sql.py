#!/usr/bin/env python3
"""Genera CSV + SQL de altas e-commerce Centralo para del_corro."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROWS = json.loads((OUT / "excel_raw.json").read_text())


def sql_str(s) -> str:
    if s is None:
        return "NULL"
    text = str(s).strip()
    if text == "":
        return "NULL"
    return "'" + text.replace("'", "''") + "'"


def sql_json(obj) -> str:
    return "'" + json.dumps(obj, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def first_name(nombre: str) -> str:
    parts = (nombre or "").strip().split()
    return parts[0] if parts else ""


def main() -> None:
    by_s: dict[str, list] = defaultdict(list)
    for r in ROWS:
        by_s[r["suffix10"]].append(r)

    chosen = []
    excel_skipped = []
    for items in by_s.values():
        items_sorted = sorted(
            items,
            key=lambda x: (
                0 if "prueba" in x["nombre"].lower() else 1,
                x["codigo_centralo"] or 0,
            ),
            reverse=True,
        )
        keep = items_sorted[0]
        chosen.append(keep)
        for skip in items_sorted[1:]:
            excel_skipped.append(
                {
                    **skip,
                    "motivo": "telefono_duplicado_excel",
                    "keeper_centralo": keep["codigo_centralo"],
                }
            )

    chosen.sort(key=lambda r: r["codigo_centralo"] or 0, reverse=True)

    csv_path = OUT / "phase-clientes-ecommerce.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "suffix10",
                "phone_canon",
                "nombre",
                "email",
                "direccion",
                "tipo_doc",
                "documento",
                "codigo_centralo",
                "accion",
            ],
        )
        w.writeheader()
        for r in chosen:
            w.writerow(
                {
                    "suffix10": r["suffix10"],
                    "phone_canon": r["phone_canon"],
                    "nombre": r["nombre"],
                    "email": r["email"],
                    "direccion": r["direccion"],
                    "tipo_doc": r["tipo_doc"],
                    "documento": r["documento"],
                    "codigo_centralo": r["codigo_centralo"],
                    "accion": "insert_si_no_existe",
                }
            )

    values_sql = []
    for r in chosen:
        tipo = (r["tipo_doc"] or "").upper()
        cuit = r["documento"] if tipo == "CUIT" else None
        dni = r["documento"] if tipo == "DNI" else None
        values_sql.append(
            "("
            + ", ".join(
                [
                    sql_str(r["suffix10"]),
                    sql_str(r["phone_canon"]),
                    sql_str(r["nombre"]),
                    sql_str(first_name(r["nombre"])),
                    sql_str(r["email"] or None),
                    sql_str(r["direccion"]),
                    sql_str(cuit),
                    sql_str(dni),
                    sql_str(r["tipo_doc"] or None),
                    str(int(r["codigo_centralo"])),
                ]
            )
            + ")"
        )

    excel_values = ",\n  ".join(values_sql)

    sql = f"""-- Tenant: del_corro
-- Altas e-commerce Centralo 2026-09-12
-- Inserta solo suffix10 que NO existen (excluye dup-merged-*).
-- Etiqueta y agrupa todos los destinos únicos para plantilla clientes_web.

WITH excel_raw(
  suffix10, phone_canon, nombre, nombre_de_pila, email, direccion, cuit,
  dni, tipo_doc, codigo_centralo
) AS (
  VALUES
  {excel_values}
),
excel AS (
  SELECT
    suffix10, phone_canon, nombre, nombre_de_pila, email, direccion, cuit,
    jsonb_strip_nulls(jsonb_build_object(
      'origen', 'ecommerce_centralo',
      'codigo_centralo', codigo_centralo,
      'tipo_documento', tipo_doc,
      'dni', dni,
      'cuit', cuit
    )) AS datos_personales,
    jsonb_build_object(
      'origen', 'ecommerce_centralo',
      'codigo_centralo', codigo_centralo,
      'import', 'altas-ecommerce-2026-09-12',
      'excel', 'Users-2026-04-24'
    ) AS metadata,
    codigo_centralo
  FROM excel_raw
),
existing AS (
  SELECT
    e.suffix10,
    c.id AS client_id,
    c.phone_number,
    c.codigo,
    row_number() OVER (
      PARTITION BY e.suffix10
      ORDER BY
        (
          lower(COALESCE(c.nombre, '') || ' ' || COALESCE(c.razon_social, ''))
          LIKE '%' || lower(split_part(e.nombre, ' ', 1)) || '%'
        ) DESC,
        (c.phone_number ~ '^549[1-9]') DESC,
        (c.codigo IS NOT NULL) DESC,
        c.id
    ) AS rn
  FROM excel e
  JOIN del_corro.clients c
    ON right(regexp_replace(COALESCE(c.phone_number, ''), '[^0-9]', '', 'g'), 10) = e.suffix10
   AND c.phone_number NOT LIKE 'dup-merged-%'
),
keepers AS (
  SELECT suffix10, client_id FROM existing WHERE rn = 1
),
to_insert AS (
  SELECT e.*
  FROM excel e
  LEFT JOIN keepers k ON k.suffix10 = e.suffix10
  WHERE k.client_id IS NULL
),
ins_clients AS (
  INSERT INTO del_corro.clients (
    phone_number, nombre, razon_social, nombre_de_pila,
    lista_precios_id, codigo, activo_ai, email, cuit,
    etiqueta, is_primary, whatsapp_estado, is_mock,
    datos_personales, metadata
  )
  SELECT
    t.phone_canon,
    t.nombre,
    t.nombre,
    t.nombre_de_pila,
    1,
    NULL,
    true,
    t.email,
    t.cuit,
    'CLIENTES_WEB',
    true,
    'no_validado',
    false,
    t.datos_personales,
    t.metadata
  FROM to_insert t
  ON CONFLICT (phone_number) DO NOTHING
  RETURNING id, phone_number
),
ins_loc AS (
  INSERT INTO del_corro.client_locations (
    client_id, address_text, is_primary, source, geocode_status, created_by
  )
  SELECT ic.id, t.direccion, true, 'ecommerce_centralo', 'pending', 'altas-ecommerce-2026-09-12'
  FROM ins_clients ic
  JOIN to_insert t ON t.phone_canon = ic.phone_number
  WHERE t.direccion IS NOT NULL
  RETURNING client_id
),
to_migrate AS (
  SELECT
    c.id,
    c.razon_social,
    c.codigo,
    c.lista_precios_id,
    c.dia_de_visita,
    c.dia_de_entrega,
    c.cuit,
    t.direccion,
    c.email,
    c.vendedor,
    c.activo_ai,
    row_number() OVER (ORDER BY c.id) AS rn
  FROM del_corro.clients c
  JOIN ins_clients ic ON ic.id = c.id
  JOIN to_insert t ON t.phone_canon = ic.phone_number
  WHERE c.pdv_id IS NULL
),
inserted_pdv AS (
  INSERT INTO del_corro.puntos_venta (
    razon_social, codigo, lista_precios_id,
    dia_de_visita, dia_de_entrega,
    cuit, direccion, email, vendedor, activo_ai
  )
  SELECT
    tm.razon_social, tm.codigo, tm.lista_precios_id,
    tm.dia_de_visita, tm.dia_de_entrega,
    tm.cuit, tm.direccion, tm.email, tm.vendedor, tm.activo_ai
  FROM to_migrate tm
  ORDER BY tm.rn
  RETURNING id
),
numbered_pdv AS (
  SELECT id, row_number() OVER (ORDER BY id) AS rn FROM inserted_pdv
),
paired AS (
  SELECT tm.id AS client_id, np.id AS pdv_id
  FROM to_migrate tm
  JOIN numbered_pdv np ON np.rn = tm.rn
),
upd_pdv AS (
  UPDATE del_corro.clients c
  SET pdv_id = p.pdv_id, updated_at = now()
  FROM paired p
  WHERE c.id = p.client_id
  RETURNING c.id
),
ensured_etiqueta AS (
  INSERT INTO del_corro.etiquetas (name, parent_id, is_starred)
  SELECT 'Clientes Web', NULL, true
  WHERE NOT EXISTS (
    SELECT 1 FROM del_corro.etiquetas WHERE name = 'Clientes Web'
  )
  RETURNING id
),
etiqueta AS (
  SELECT id FROM ensured_etiqueta
  UNION ALL
  SELECT id FROM del_corro.etiquetas WHERE name = 'Clientes Web'
  LIMIT 1
),
all_targets AS (
  SELECT client_id FROM keepers
  UNION
  SELECT id FROM ins_clients
),
ins_tags AS (
  INSERT INTO del_corro.clientes_etiquetas (client_id, etiqueta_id)
  SELECT t.client_id, e.id
  FROM all_targets t
  CROSS JOIN etiqueta e
  ON CONFLICT DO NOTHING
  RETURNING client_id
),
ensured_grupo AS (
  INSERT INTO del_corro.grupos (nombre, etiqueta_ids, activo_ai)
  SELECT 'Clientes Web e-commerce', ARRAY[e.id], true
  FROM etiqueta e
  WHERE NOT EXISTS (
    SELECT 1 FROM del_corro.grupos WHERE nombre = 'Clientes Web e-commerce'
  )
  RETURNING id
),
grupo AS (
  SELECT id FROM ensured_grupo
  UNION ALL
  SELECT id FROM del_corro.grupos WHERE nombre = 'Clientes Web e-commerce'
  LIMIT 1
),
ins_agenda AS (
  INSERT INTO del_corro.agenda (
    grupo_id, meta_plantilla_id, tipo, hora_envio, fecha_programada,
    activo, origen
  )
  SELECT
    g.id,
    '384f5f6f-74a1-4d46-aa00-b9af2d76af35'::uuid,
    'puntual',
    TIME '11:30',
    DATE '2026-09-12',
    true,
    'ecommerce_welcome'
  FROM grupo g
  WHERE NOT EXISTS (
    SELECT 1
    FROM del_corro.agenda a
    WHERE a.origen = 'ecommerce_welcome'
      AND a.fecha_programada = DATE '2026-09-12'
      AND a.meta_plantilla_id = '384f5f6f-74a1-4d46-aa00-b9af2d76af35'::uuid
  )
  RETURNING id
)
SELECT json_build_object(
  'excel_unicos', (SELECT COUNT(*) FROM excel),
  'existentes_tagged', (SELECT COUNT(*) FROM keepers),
  'insertados', (SELECT COUNT(*) FROM ins_clients),
  'locations', (SELECT COUNT(*) FROM ins_loc),
  'pdvs', (SELECT COUNT(*) FROM inserted_pdv),
  'tags', (SELECT COUNT(*) FROM ins_tags),
  'etiqueta_id', (SELECT id FROM etiqueta),
  'grupo_id', (SELECT id FROM grupo),
  'agenda_id', (SELECT id FROM ins_agenda)
) AS resultado;
"""

    (OUT / "cargar_altas.sql").write_text(sql)
    (OUT / "excel_skipped.json").write_text(
        json.dumps(excel_skipped, ensure_ascii=False, indent=2)
    )
    print(f"chosen={len(chosen)} skipped={len(excel_skipped)}")
    print(f"sql_bytes={len(sql)}")
    print(csv_path)
    print(OUT / "cargar_altas.sql")


if __name__ == "__main__":
    main()
