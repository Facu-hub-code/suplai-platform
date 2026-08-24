"""
Curar tenant demo para videollamadas de ventas (SPEC-035).

Uso (desde suplai-platform, con SUPABASE_DB_URL del backend):

    python scripts/demo-videollamadas/curar_tenant_demo.py --esquema demo
    python scripts/demo-videollamadas/curar_tenant_demo.py --esquema demo --skip-field
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import yaml
from dotenv import load_dotenv

SCHEMA_ALLOWED = "demo"
ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env")
OUTPUTS = ROOT / "implementacion" / "demo" / "outputs"

HQ = {"label": "Central Demo — Chacarita", "latitude": -34.5885, "longitude": -58.4545}

# (lng, lat) rings — irregular, closed by repeating first point
ZONAS = [
    {
        "id": 14,
        "name": "Palermo",
        "color": "#E63946",
        "dia": "lunes",
        "dias_extra": ["sabado"],
        "vendedor_id": 10,
        "ring": [
            (-58.425, -34.572), (-58.405, -34.575), (-58.400, -34.588),
            (-58.418, -34.598), (-58.438, -34.592), (-58.442, -34.578),
        ],
    },
    {
        "id": 15,
        "name": "Belgrano",
        "color": "#2A9D8F",
        "dia": "martes",
        "dias_extra": [],
        "vendedor_id": 11,
        "ring": [
            (-58.462, -34.548), (-58.438, -34.545), (-58.428, -34.558),
            (-58.435, -34.568), (-58.458, -34.565), (-58.468, -34.555),
        ],
    },
    {
        "id": 1,
        "name": "Colegiales",
        "color": "#457B9D",
        "dia": "miercoles",
        "dias_extra": [],
        "vendedor_id": 11,
        "ring": [
            (-58.458, -34.568), (-58.440, -34.566), (-58.432, -34.576),
            (-58.440, -34.585), (-58.455, -34.583), (-58.462, -34.575),
        ],
    },
    {
        "id": 16,
        "name": "Villa Crespo",
        "color": "#E9C46A",
        "dia": "jueves",
        "dias_extra": [],
        "vendedor_id": 12,
        "ring": [
            (-58.452, -34.590), (-58.432, -34.588), (-58.425, -34.600),
            (-58.438, -34.610), (-58.455, -34.606), (-58.460, -34.596),
        ],
    },
    {
        "id": 17,
        "name": "Caballito",
        "color": "#9B5DE5",
        "dia": "viernes",
        "dias_extra": ["sabado"],
        "vendedor_id": 12,
        "ring": [
            (-58.452, -34.608), (-58.430, -34.606), (-58.422, -34.620),
            (-58.435, -34.630), (-58.455, -34.628), (-58.462, -34.616),
        ],
    },
]

VENDEDORES = [
    (10, "Lucía Martínez", "5491145123401", "lucia.martinez@suplaisales.mock", "PALERMO"),
    (11, "Martín Álvarez", "5491145123402", "martin.alvarez@suplaisales.mock", "NORTE"),
    (12, "Sofía Romero", "5491145123403", "sofia.romero@suplaisales.mock", "OESTE"),
]

CALLES = {
    "Palermo": ["Av. Santa Fe", "Thames", "Honduras", "Scalabrini Ortiz", "Gorriti"],
    "Belgrano": ["Av. Cabildo", "Juramento", "Monroe", "Olazábal", "Cuba"],
    "Colegiales": ["Av. Elcano", "Alvarez Thomas", "Céspedes", "Conde", "Maure"],
    "Villa Crespo": ["Av. Corrientes", "Warnes", "Acevedo", "Serrano", "Murillo"],
    "Caballito": ["Av. Rivadavia", "Acoyte", "Pedro Goyena", "Directorio", "Yerbal"],
}

INACTIVE_ZONE_IDS = (18, 19, 20)
INACTIVE_SELLER_IDS = (1, 2, 3)
KEEP_SELLER_IDS = (10, 11, 12)


def _load_env() -> None:
    load_dotenv(ROOT / ".env", override=False)
    if BACKEND_ENV.exists():
        load_dotenv(BACKEND_ENV, override=False)


def _db_url() -> str:
    raw = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_DB_URL_POOLER") or ""
    if not raw:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no configurada")
    return raw.replace(":5432/", ":6543/")


def _wkt(ring: list[tuple[float, float]]) -> str:
    pts = ring + [ring[0]]
    body = ", ".join(f"{lng} {lat}" for lng, lat in pts)
    return f"MULTIPOLYGON((({body})))"


def _point_in(rng: random.Random, ring: list[tuple[float, float]]) -> tuple[float, float]:
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    vertex = ring[rng.randrange(len(ring))]
    t = 0.15 + rng.random() * 0.55
    lng = cx + t * (vertex[0] - cx)
    lat = cy + t * (vertex[1] - cy)
    return lat, lng


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


async def curar(schema: str, skip_field: bool) -> None:
    if schema != SCHEMA_ALLOWED:
        raise SystemExit(f"[FAIL] Este script solo corre sobre schema '{SCHEMA_ALLOWED}', recibido '{schema}'")

    print(f"[*] schema_name confirmado: {schema}")
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    rng = random.Random(42)
    today = date.today()
    try:
        await conn.execute("SET search_path TO demo, core, public, extensions")

        # ------------------------------------------------------------------
        # 1. Catálogo 250
        # ------------------------------------------------------------------
        print("[*] Seleccionando 70 clientes y 250 SKUs...")
        keep_clients = await conn.fetch(
            """
            SELECT c.id, c.nombre, c.razon_social, c.phone_number, c.pdv_id,
                   c.lista_precios_id, c.direccion, c.email, c.cuit,
                   COUNT(p.id) FILTER (WHERE p.deleted_at IS NULL) AS n_pedidos
            FROM demo.clients c
            LEFT JOIN demo.pedidos p ON p.cliente_id = c.id
            GROUP BY c.id
            ORDER BY n_pedidos DESC, c.id
            LIMIT 70
            """
        )
        client_ids = [int(r["id"]) for r in keep_clients]
        if len(client_ids) != 70:
            raise SystemExit(f"[FAIL] Se esperaban 70 clientes, hay {len(client_ids)}")

        skus = await conn.fetch(
            """
            WITH sold AS (
              SELECT ip.product_code, SUM(COALESCE(ip.cantidad_solicitada, 0)) AS qty
              FROM demo.items_pedido ip
              JOIN demo.pedidos p ON p.id = ip.pedido_id
              WHERE p.cliente_id = ANY($1::int[])
                AND p.deleted_at IS NULL
              GROUP BY ip.product_code
            )
            SELECT p.product_code, p.nombre, p.image_url, p.descripcion, p.rotacion_index,
                   COALESCE(s.qty, 0) AS qty
            FROM demo.productos p
            LEFT JOIN sold s ON s.product_code = p.product_code
            WHERE p.image_url IS NOT NULL AND btrim(p.image_url) <> ''
              AND p.descripcion IS NOT NULL AND btrim(p.descripcion) <> ''
            ORDER BY (s.qty > 0) DESC, s.qty DESC, p.rotacion_index DESC NULLS LAST, p.product_code
            LIMIT 250
            """,
            client_ids,
        )
        sku_codes = [r["product_code"] for r in skus]
        if len(sku_codes) != 250:
            raise SystemExit(f"[FAIL] Se esperaban 250 SKUs con imagen+desc, hay {len(sku_codes)}")

        await conn.execute(
            """
            UPDATE demo.productos
            SET en_catalogo = (product_code = ANY($1::text[])),
                updated_at = now()
            """,
            sku_codes,
        )
        # El recorte físico (DELETE de SKUs fuera de catálogo) lo hace
        # higiene_tenant_demo.py para no reintroducir filas ocultas en el backoffice.

        tag_row = await conn.fetchrow("SELECT id FROM demo.tags ORDER BY id LIMIT 1")
        if tag_row:
            await conn.execute(
                """
                INSERT INTO demo.product_tags (product_code, tag_id)
                SELECT p.product_code, $2
                FROM demo.productos p
                WHERE p.product_code = ANY($1::text[])
                  AND NOT EXISTS (
                    SELECT 1 FROM demo.product_tags pt
                    WHERE pt.product_code = p.product_code
                  )
                ON CONFLICT DO NOTHING
                """,
                sku_codes,
                int(tag_row["id"]),
            )

        await conn.execute(
            """
            UPDATE demo.listas_precios SET
              activa = true,
              es_publica = true,
              nombre = CASE id
                WHEN 1 THEN 'Lista 1'
                WHEN 2 THEN 'Lista 2'
                WHEN 3 THEN 'Lista 3'
                WHEN 4 THEN 'Lista 4'
                ELSE nombre
              END,
              updated_at = now()
            WHERE id IN (1,2,3,4)
            """
        )
        multipliers = {1: 1.00, 2: 1.15, 3: 0.90, 4: 0.85}
        for lista_id, mult in multipliers.items():
            await conn.execute(
                """
                INSERT INTO demo.precios_productos (product_code, lista_precios_id, precio_unidad, is_mock)
                SELECT b.product_code, $2, ROUND((b.precio_unidad * $3)::numeric, 2), true
                FROM demo.precios_productos b
                WHERE b.lista_precios_id = 1
                  AND b.product_code = ANY($1::text[])
                ON CONFLICT (product_code, lista_precios_id) DO UPDATE
                  SET precio_unidad = EXCLUDED.precio_unidad, updated_at = now()
                """,
                sku_codes,
                lista_id,
                mult,
            )

        _write_csv(
            OUTPUTS / "phase-01-productos-curados.csv",
            [dict(r) for r in skus],
            ["product_code", "nombre", "image_url", "descripcion", "rotacion_index", "qty"],
        )
        n_cat = await conn.fetchval("SELECT COUNT(*) FROM demo.productos WHERE en_catalogo = true")
        print(f"[OK] Catálogo en_catalogo=true: {n_cat}")

        # ------------------------------------------------------------------
        # 2. Red comercial
        # ------------------------------------------------------------------
        n_loc_exist = await conn.fetchval("SELECT COUNT(DISTINCT client_id) FROM demo.client_locations")
        skip_map = n_loc_exist >= 70
        print("[*] Actualizando vendedores y zonas CABA...")
        for vid, nombre, tel, email, zona in VENDEDORES:
            await conn.execute(
                """
                UPDATE demo.vendedores
                SET nombre=$2, telefono=$3, email=$4, zona=$5, activo=true, is_mock=true, updated_at=now()
                WHERE id=$1
                """,
                vid, nombre, tel, email, zona,
            )
        # Vendedores 1/2/3 se borran en higiene_tenant_demo.py (no solo activo=false).

        if skip_map:
            print("[SKIP] Polígonos y pines ya curados — no se reescriben zonas.")
        else:
            for z in ZONAS:
                dias = [z["dia"], *z["dias_extra"]]
                await conn.execute(
                    """
                    UPDATE demo.geo_zones SET
                      name=$2,
                      zone_type='sales',
                      color=$3,
                      dia_visita=$4::core.dia_de_visita_enum,
                      dias_visita=$5::core.dia_de_visita_enum[],
                      vendedor_principal_id=$6,
                      geometry=ST_Multi(ST_GeomFromText($7, 4326)),
                      active=true,
                      is_mock=true,
                      description=$8,
                      updated_at=now()
                    WHERE id=$1
                    """,
                    z["id"], z["name"], z["color"], z["dia"], dias, z["vendedor_id"],
                    _wkt(z["ring"]), f"Barrio {z['name']} — CABA",
                )

            await conn.execute(
                "UPDATE demo.geo_zones SET active=false, updated_at=now() WHERE id = ANY($1::int[])",
                list(INACTIVE_ZONE_IDS),
            )

            await conn.execute("UPDATE demo.vendedor_geo_zones SET activo=false")
            for z in ZONAS:
                await conn.execute(
                    """
                    INSERT INTO demo.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, true)
                    ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE
                      SET activo=true, is_mock=true, updated_at=now()
                    """,
                    z["vendedor_id"], z["id"],
                )

        assignments: list[tuple[int, dict]] = []
        per_zone = 14
        for i, client in enumerate(keep_clients):
            z = ZONAS[i // per_zone]
            assignments.append((int(client["id"]), z))

        if skip_map:
            print("[SKIP] Mapa ya curado (70 pines). No se reubican clientes.")
            client_rows_csv = []
        else:
            print("[*] Reubicando 70 clientes...")
            await conn.execute("UPDATE demo.clients SET is_primary=false WHERE pdv_id IS NOT NULL")
        if not skip_map:
            await conn.execute(
                """
                DELETE FROM demo.client_locations
                WHERE client_id <> ALL($1::int[])
                """,
                client_ids,
            )
            await conn.execute(
                "UPDATE demo.vendedores_clientes SET activo=false WHERE cliente_id <> ALL($1::int[])",
                client_ids,
            )
            await conn.execute(
                "DELETE FROM demo.vendedores_clientes WHERE cliente_id = ANY($1::int[])",
                client_ids,
            )

            client_rows_csv = []
            seen_pdv: set[int] = set()
            for cid, z in assignments:
                lat, lng = _point_in(rng, z["ring"])
                calle = rng.choice(CALLES[z["name"]])
                altura = rng.randint(800, 4800)
                direccion = f"{calle} {altura}, {z['name']}, CABA"
                lista_id = 1 + (cid % 4)
                src = next(c for c in keep_clients if int(c["id"]) == cid)
                nombre = src["nombre"] or src["razon_social"] or f"Kiosco {z['name']} {cid}"
                razon = src["razon_social"] or nombre
                phone = src["phone_number"] or f"54911{4000000 + cid}"
                email = src["email"] or f"cliente{cid}@suplaisales.mock"
                cuit = src["cuit"] or f"30-{20000000 + cid}-9"

                pdv_id = src["pdv_id"]
                vendedor_nombre = next(v[1] for v in VENDEDORES if v[0] == z["vendedor_id"])
                reuse_pdv = bool(pdv_id) and int(pdv_id) not in seen_pdv
                if reuse_pdv:
                    await conn.execute(
                        """
                        UPDATE demo.puntos_venta SET
                          razon_social=$2, direccion=$3, email=$4, vendedor=$5,
                          geo_zone_id=$6, vendedor_id=$7, lista_precios_id=$8,
                          dia_de_visita=$9::core.dia_de_visita_enum,
                          activo_ai=true, is_mock=true, updated_at=now()
                        WHERE id=$1
                        """,
                        int(pdv_id), razon, direccion, email, vendedor_nombre,
                        z["id"], z["vendedor_id"], lista_id, z["dia"],
                    )
                    seen_pdv.add(int(pdv_id))
                else:
                    pdv_id = await conn.fetchval(
                        """
                        INSERT INTO demo.puntos_venta
                          (razon_social, codigo, lista_precios_id, dia_de_visita, direccion,
                           email, vendedor, activo_ai, geo_zone_id, vendedor_id, is_mock)
                        VALUES ($1, $2, $3, $4::core.dia_de_visita_enum, $5, $6, $7, true, $8, $9, true)
                        RETURNING id
                        """,
                        razon, 90000 + cid, lista_id, z["dia"], direccion, email,
                        vendedor_nombre,
                        z["id"], z["vendedor_id"],
                    )
                    seen_pdv.add(int(pdv_id))

                is_prospect = assignments.index((cid, z)) >= 56
                await conn.execute(
                    """
                    UPDATE demo.clients SET
                      nombre=$2, razon_social=$3, phone_number=$4, email=$5, cuit=$6,
                      direccion=$7, lista_precios_id=$8, pdv_id=$9, is_primary=true,
                      activo_ai = NOT $10,
                      etiqueta = CASE WHEN $10 THEN 'PROSPECTO' ELSE NULL END,
                      whatsapp_estado = CASE WHEN $10 THEN 'no_validado' ELSE 'validado' END::whatsapp_estado_cliente_enum,
                      whatsapp_validado_at = CASE WHEN $10 THEN NULL ELSE now() END,
                      vendedor=$11, dia_de_visita=$12::core.dia_de_visita_enum,
                      is_mock=true, updated_at=now()
                    WHERE id=$1
                    """,
                    cid, nombre, razon, phone, email, cuit, direccion, lista_id, int(pdv_id),
                    is_prospect,
                    next(v[1] for v in VENDEDORES if v[0] == z["vendedor_id"]),
                    z["dia"],
                )
                await conn.execute(
                    """
                    INSERT INTO demo.vendedores_clientes (vendedor_id, cliente_id, activo)
                    VALUES ($1, $2, true)
                    """,
                    z["vendedor_id"], cid,
                )
                existing_loc = await conn.fetchval(
                    "SELECT id FROM demo.client_locations WHERE client_id=$1 LIMIT 1", cid
                )
                loc_sql_common = """
                    client_id=$1, source='backoffice', latitude=$2, longitude=$3,
                    location=ST_SetSRID(ST_MakePoint($3, $2), 4326),
                    address_text=$4, name=$5, is_primary=true, geocode_status='resolved',
                    updated_at=now()
                """
                if existing_loc:
                    await conn.execute(
                        f"UPDATE demo.client_locations SET {loc_sql_common} WHERE id=$6",
                        cid, lat, lng, direccion, razon, int(existing_loc),
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO demo.client_locations
                          (client_id, source, latitude, longitude, location, address_text,
                           name, is_primary, geocode_status)
                        VALUES ($1, 'backoffice', $2, $3,
                                ST_SetSRID(ST_MakePoint($3, $2), 4326), $4, $5, true, 'resolved')
                        """,
                        cid, lat, lng, direccion, razon,
                    )
                client_rows_csv.append({
                    "cliente_id": cid,
                    "nombre": nombre,
                    "barrio": z["name"],
                    "vendedor_id": z["vendedor_id"],
                    "lat": round(lat, 6),
                    "lng": round(lng, 6),
                    "prospecto": is_prospect,
                })

            # Clientes extra: DELETE físico en higiene_tenant_demo.py (no ocultar).

            _write_csv(
                OUTPUTS / "phase-04-clientes.csv",
                client_rows_csv,
                ["cliente_id", "nombre", "barrio", "vendedor_id", "lat", "lng", "prospecto"],
            )

        # HQ
        print("[*] Seteando HQ Chacarita en reglas_negocio...")
        await conn.execute(
            """
            UPDATE public.distribuidoras
            SET reglas_negocio = COALESCE(reglas_negocio::jsonb, '{}'::jsonb)
              || jsonb_build_object(
                   'order_fulfillment',
                   jsonb_build_object(
                     'location_hub', jsonb_build_object(
                       'label', $1::text,
                       'latitude', $2::float8,
                       'longitude', $3::float8
                     )
                   )
                 ),
                updated_at = now()
            WHERE schema_name = 'demo'
            """,
            HQ["label"], HQ["latitude"], HQ["longitude"],
        )

        # ------------------------------------------------------------------
        # 3. Promos vigentes
        # ------------------------------------------------------------------
        print("[*] Actualizando promociones vigentes...")
        promo_skus = sku_codes[:6]
        promo_start = datetime.combine(today - timedelta(days=2), datetime.min.time())
        promo_end = datetime.combine(today + timedelta(days=12), datetime.min.time())
        existing_promos = await conn.fetch(
            "SELECT id FROM demo.promociones_semanales ORDER BY id LIMIT 6"
        )
        for i, row in enumerate(existing_promos):
            code = promo_skus[i % len(promo_skus)]
            pname = next(s["nombre"] for s in skus if s["product_code"] == code)
            await conn.execute(
                """
                UPDATE demo.promociones_semanales SET
                  product_code=$2, product_name=$3,
                  fecha_inicio=$4, fecha_fin=$5,
                  lista_precios_id=1, is_mock=true, updated_at=now()
                WHERE id=$1
                """,
                int(row["id"]), code, pname, promo_start, promo_end,
            )

        # ------------------------------------------------------------------
        # 4. Conversaciones + tickets
        # ------------------------------------------------------------------
        print("[SKIP] Conversaciones e insights existentes no se reescriben.")
        print("[*] Recortes DELETE + reclamos + prompt v2: higiene_tenant_demo.py")

        # ------------------------------------------------------------------
        # 5. Función de shift
        # ------------------------------------------------------------------
        sql_path = Path(__file__).with_name("shift_fechas.sql")
        await conn.execute(sql_path.read_text(encoding="utf-8"))
        shift = await conn.fetchval("SELECT demo.shift_sales_demo_dates()")
        print(f"[OK] shift_sales_demo_dates → {shift}")

        await conn.execute(
            "UPDATE demo.field_tournaments SET estado='CERRADO', updated_at=now() WHERE estado='ACTIVO'"
        )

        n_loc = await conn.fetchval(
            "SELECT COUNT(*) FROM demo.client_locations WHERE client_id = ANY($1::int[])",
            client_ids,
        )
        n_zonas = await conn.fetchval("SELECT COUNT(*) FROM demo.geo_zones WHERE active=true")
        n_vend = await conn.fetchval("SELECT COUNT(*) FROM demo.vendedores WHERE activo=true")
        print(f"[OK] locations={n_loc} zonas_activas={n_zonas} vendedores_activos={n_vend}")

    finally:
        await conn.close()

    higiene = Path(__file__).with_name("higiene_tenant_demo.py")
    print(f"\n>>> {sys.executable} {higiene} --esquema {schema}")
    rc_h = subprocess.run(
        [sys.executable, str(higiene), "--esquema", schema],
        cwd=str(ROOT),
        env={**os.environ, "SUPABASE_DB_URL": _db_url()},
    )
    if rc_h.returncode != 0:
        print(f"[WARN] higiene_tenant_demo falló ({rc_h.returncode})")

    if skip_field:
        print("[SKIP] Field setup omitido (--skip-field)")
        return

    py = sys.executable
    env = os.environ.copy()
    env["SUPABASE_DB_URL"] = _db_url()
    field_dir = ROOT / "scripts" / "fase-06-1-field"
    steps = [
        [py, str(field_dir / "setup_templates.py"), "--esquema", schema],
        [py, str(field_dir / "setup_objetivos.py"), "--esquema", schema, "--limpiar"],
        [py, str(field_dir / "setup_torneo.py"), "--esquema", schema, "--forzar"],
        [py, str(field_dir / "retrain_ml.py"), "--esquema", schema],
        [py, str(field_dir / "seed_tareas_historicas.py"), "--esquema", schema, "--dias", "30"],
        [py, str(field_dir / "trigger_tareas.py"), "--esquema", schema, "--dias", "6"],
    ]
    for cmd in steps:
        print(f"\n>>> {' '.join(cmd)}")
        rc = subprocess.run(cmd, cwd=str(ROOT), env=env)
        if rc.returncode != 0:
            print(f"[WARN] paso Field falló ({rc.returncode}): {cmd[1]}")


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--esquema", default="demo")
    parser.add_argument("--skip-field", action="store_true")
    args = parser.parse_args()
    asyncio.run(curar(args.esquema, args.skip_field))


if __name__ == "__main__":
    main()
