#!/usr/bin/env python3
"""Reemplaza la demo de esekau por catálogo y red comercial reales.

schema_name = esekau (confirmado: confirmar carga).
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import unicodedata
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "esekau"
TENANT_ID = "4189dcf1-6ed4-48f8-a2a1-a2b190b6a245"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _load_envs() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT.parent / "backend-supabase" / ".env",
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
            print(f"[*] env: {path}")
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    url = force_pooler(url)
    if url:
        os.environ["SUPABASE_DB_URL"] = url
        os.environ["SUPABASE_DB_URL_POOLER"] = url


_load_envs()


def normalizar_alias(alias_raw: str) -> str:
    alias_flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    ascii_txt = alias_flat.encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in ascii_txt if c.isalnum())


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


async def _exec(conn: asyncpg.Connection, sql: str, *args) -> None:
    await conn.execute(sql, *args)


async def limpiar_demo(conn: asyncpg.Connection) -> None:
    print(f"[*] Limpiando demo mock en {SCHEMA}...")
    await conn.execute(f"SET search_path TO {SCHEMA}, core, public, extensions")
    stmts = [
        f"DELETE FROM {SCHEMA}.field_task_events",
        f"DELETE FROM {SCHEMA}.field_point_ledger",
        f"DELETE FROM {SCHEMA}.field_tasks",
        f"DELETE FROM {SCHEMA}.field_objetivo_skus",
        f"DELETE FROM {SCHEMA}.field_objetivos",
        f"DELETE FROM {SCHEMA}.items_pedido",
        f"DELETE FROM {SCHEMA}.pedidos",
        f"DELETE FROM {SCHEMA}.promocion_grupo_productos",
        f"DELETE FROM {SCHEMA}.promociones_semanales",
        f"DELETE FROM {SCHEMA}.client_locations",
        f"DELETE FROM {SCHEMA}.client_operating_profiles",
        f"DELETE FROM {SCHEMA}.client_product_memory",
        f"DELETE FROM {SCHEMA}.cliente_producto_favorito",
        f"DELETE FROM {SCHEMA}.clientes_aliases",
        f"DELETE FROM {SCHEMA}.clientes_etiquetas",
        f"DELETE FROM {SCHEMA}.vendedores_clientes",
        f"DELETE FROM {SCHEMA}.prospect_profiles",
        f"DELETE FROM {SCHEMA}.routes_clients",
        f"DELETE FROM {SCHEMA}.agenda",
        f"DELETE FROM {SCHEMA}.ia_tickets",
        f"DELETE FROM {SCHEMA}.conversations",
        f"DELETE FROM {SCHEMA}.campaign_prospect",
        f"DELETE FROM {SCHEMA}.campaign_cost_daily",
        f"DELETE FROM {SCHEMA}.funnel_daily",
        f"DELETE FROM {SCHEMA}.campaign_export",
        f"DELETE FROM {SCHEMA}.campaign_template",
        f"DELETE FROM {SCHEMA}.campaign",
        f"DELETE FROM {SCHEMA}.estrategia_dispatch_replies",
        f"DELETE FROM {SCHEMA}.estrategia_dispatches",
        f"DELETE FROM {SCHEMA}.estrategia_member_state",
        f"DELETE FROM {SCHEMA}.estrategia_schedule_decisions",
        f"DELETE FROM {SCHEMA}.estrategia_cohort_members",
        f"DELETE FROM {SCHEMA}.clients",
        f"DELETE FROM {SCHEMA}.puntos_venta",
        f"DELETE FROM {SCHEMA}.vendedor_geo_zones",
        f"DELETE FROM {SCHEMA}.geo_zones",
        f"DELETE FROM {SCHEMA}.vendedores",
        f"DELETE FROM {SCHEMA}.product_categories",
        f"DELETE FROM {SCHEMA}.product_tags",
        f"DELETE FROM {SCHEMA}.productos_aliases",
        f"DELETE FROM {SCHEMA}.precios_productos",
        f"DELETE FROM {SCHEMA}.documents",
        f"DELETE FROM {SCHEMA}.productos",
        "DELETE FROM public.tenant_cross_sell_mappings WHERE tenant_id = $1::uuid",
        "DELETE FROM public.tenant_up_sell_mappings WHERE tenant_id = $1::uuid",
    ]
    for sql in stmts:
        try:
            if "$1" in sql:
                await conn.execute(sql, TENANT_ID)
            else:
                await conn.execute(sql)
        except Exception as exc:
            print(f"[WARN] limpieza: {sql[:80]} → {exc}")
    print("[*] Demo operativa borrada (catálogo, red, pedidos, field, mappings).")


async def cargar() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] tenant destino: {SCHEMA} (producción, reemplazo de demo)")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    products = list(csv.DictReader((OUT / "phase-01-productos.csv").open(encoding="utf-8")))
    prices = list(csv.DictReader((OUT / "phase-01-lista-precios-1.csv").open(encoding="utf-8")))
    vendedores = list(csv.DictReader((OUT / "phase-04-vendedores.csv").open(encoding="utf-8")))
    zonas = list(csv.DictReader((OUT / "phase-04-zonas.csv").open(encoding="utf-8")))
    clientes = list(csv.DictReader((OUT / "phase-04-clientes.csv").open(encoding="utf-8")))
    print(
        f"[*] CSV productos={len(products)} precios={len(prices)} "
        f"vendedores={len(vendedores)} zonas={len(zonas)} clientes={len(clientes)}"
    )
    if len(products) < 1000 or len(clientes) != 239 or len(zonas) != 5:
        print("[FAIL] Conteos CSV fuera de lo esperado (≈1217 / 5 / 239)", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        already = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE NOT is_mock) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.geo_zones WHERE NOT is_mock) AS zonas,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores WHERE NOT is_mock) AS vendedores,
              (SELECT COUNT(*) FROM {SCHEMA}.clients) AS clients
            """
        )
        resume_red = (
            int(already["productos"]) == len(products)
            and int(already["zonas"]) == 5
            and int(already["vendedores"]) == 1
        )
        if resume_red:
            print(f"[*] Resume: catálogo y zonas ya están. Limpio clientes parciales ({already['clients']}).")
            await conn.execute(f"DELETE FROM {SCHEMA}.client_locations")
            await conn.execute(f"DELETE FROM {SCHEMA}.vendedores_clientes")
            await conn.execute(f"DELETE FROM {SCHEMA}.clients")
            await conn.execute(f"DELETE FROM {SCHEMA}.puntos_venta")
        else:
            await limpiar_demo(conn)
            leftover = await conn.fetchrow(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
                  (SELECT COUNT(*) FROM {SCHEMA}.clients) AS clients,
                  (SELECT COUNT(*) FROM {SCHEMA}.pedidos) AS pedidos,
                  (SELECT COUNT(*) FROM {SCHEMA}.geo_zones) AS zonas
                """
            )
            if any(leftover[k] for k in leftover.keys()):
                print(f"[FAIL] Quedaron filas demo: {dict(leftover)}", file=sys.stderr)
                return 1

        product_codes = [p["product_code"].strip() for p in products]
        vrow = vendedores[0]
        vendedor_id = None
        zona_ids: dict[str, int] = {}

        if resume_red:
            vendedor_id = await conn.fetchval(f"SELECT id FROM {SCHEMA}.vendedores WHERE NOT is_mock ORDER BY id LIMIT 1")
            zona_rows = await conn.fetch(
                f"SELECT id, codigo_ruta FROM {SCHEMA}.geo_zones WHERE NOT is_mock"
            )
            zona_ids = {r["codigo_ruta"]: r["id"] for r in zona_rows}
            print(f"[*] Resume vendedor_id={vendedor_id} zonas={zona_ids}")
        else:
            await conn.execute(
            f"""
            INSERT INTO {SCHEMA}.listas_precios
              (id, nombre, descripcion, activa, es_publica, is_mock, created_at, updated_at)
            OVERRIDING SYSTEM VALUE
            VALUES (1, 'Lista Base Córdoba', 'Lista de precios ESEKA-U Córdoba (c/dto + impuestos)', true, true, false, now(), now())
            ON CONFLICT (id) DO UPDATE SET
              nombre = EXCLUDED.nombre,
              descripcion = EXCLUDED.descripcion,
              activa = true,
              es_publica = true,
              is_mock = false,
              updated_at = now()
            """
        )
        await conn.execute(
            f"UPDATE {SCHEMA}.listas_precios SET activa = false, es_publica = false, is_mock = false, updated_at = now() WHERE id <> 1"
        )
        await conn.execute(
            "UPDATE public.distribuidoras SET default_lista_precios = 1, updated_at = now() WHERE schema_name = $1",
            SCHEMA,
        )

        products_data = []
        aliases_data = []
        product_codes: list[str] = []
        seen_alias: set[tuple[str, str]] = set()
        for p in products:
            code = p["product_code"].strip()
            product_codes.append(code)
            products_data.append(
                (
                    code,
                    p["nombre"],
                    p.get("descripcion") or None,
                    None,
                    int(float(p["stock"])) if p.get("stock") else 0,
                    int(float(p["unidades_por_bulto"])) if p.get("unidades_por_bulto") else 1,
                    "unidad",
                    "unidad",
                    float(p["rotacion_index"]) if p.get("rotacion_index") else 0.1,
                    float(p["mental_priority"]) if p.get("mental_priority") else 0.0,
                    True,
                    False,
                )
            )
            for raw in (p.get("aliases") or "").split("|"):
                raw = raw.strip()
                if not raw:
                    continue
                norm = normalizar_alias(raw)
                if not norm:
                    continue
                key = (norm, code)
                if key in seen_alias:
                    continue
                seen_alias.add(key)
                aliases_data.append((code, raw, norm, 1.0))

        print(f"[*] Insertando {len(products_data)} productos en {SCHEMA}...")
        for i in range(0, len(products_data), BATCH):
            chunk = products_data[i : i + BATCH]
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.productos (
                    product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                    unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority,
                    en_catalogo, is_mock, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, now(), now())
                """,
                chunk,
            )
            print(f"    productos {i + 1}–{i + len(chunk)}")

        print(f"[*] Insertando {len(aliases_data)} aliases en {SCHEMA}...")
        for i in range(0, len(aliases_data), BATCH):
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.productos_aliases (
                    product_code, alias_raw, alias_norm, weight, created_at, updated_at
                ) VALUES ($1,$2,$3,$4, now(), now())
                ON CONFLICT (alias_norm, product_code) DO NOTHING
                """,
                aliases_data[i : i + BATCH],
            )

        prices_data = [
            (row["product_code"].strip(), 1, float(row["precio_unidad"]), False) for row in prices
        ]
        print(f"[*] Insertando {len(prices_data)} precios lista 1...")
        for i in range(0, len(prices_data), BATCH):
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.precios_productos (
                    product_code, lista_precios_id, precio_unidad, is_mock
                ) VALUES ($1,$2,$3,$4)
                """,
                prices_data[i : i + BATCH],
            )

        vrow = vendedores[0]
        vendedor_id = await conn.fetchval(
            f"""
            INSERT INTO {SCHEMA}.vendedores
                (nombre, telefono, email, zona, codigo_ruta, activo, is_mock)
            VALUES ($1,$2,$3,$4,$5,true,false)
            RETURNING id
            """,
            vrow["nombre"],
            vrow["telefono"],
            vrow["email"],
            vrow["zona"],
            vrow["codigo_ruta"],
        )
        print(f"[*] Vendedor {vrow['nombre']} id={vendedor_id} tel={vrow['telefono']}")

        zona_ids: dict[str, int] = {}
        for z in zonas:
            gzid = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.geo_zones
                    (name, zone_type, description, color, dia_visita, codigo_ruta,
                     vendedor_principal_id, geometry, active, is_mock, metadata)
                VALUES (
                    $1, $2, $3, $4, $5::core.dia_de_visita_enum, $6, $7,
                    extensions.ST_GeomFromEWKT($8), true, false,
                    jsonb_build_object('n_clientes_origen', $9::int)
                )
                RETURNING id
                """,
                z["nombre"],
                z.get("zone_type") or "sales",
                z.get("description") or "",
                z["color_hex"],
                z["dia_visita"],
                z["zona_codigo"],
                vendedor_id,
                z["geometry_wkt"],
                int(z.get("n_clientes_origen") or 0),
            )
            zona_ids[z["zona_codigo"]] = gzid
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.vendedor_geo_zones
                    (vendedor_id, geo_zone_id, activo, is_mock)
                VALUES ($1,$2,true,false)
                """,
                vendedor_id,
                gzid,
            )
            print(f"    zona {z['nombre']} id={gzid} dia={z['dia_visita']}")

        print(f"[*] Insertando {len(clientes)} clientes cartera...")
        for i in range(0, len(clientes), BATCH):
            chunk = clientes[i : i + BATCH]
            for row in chunk:
                codigo = int(float(row["cliente_codigo"]))
                geo_zone_id = zona_ids[row["zona_codigo"]]
                pdv_id = await conn.fetchval(
                    f"""
                    INSERT INTO {SCHEMA}.puntos_venta
                        (razon_social, codigo, lista_precios_id, dia_de_visita,
                         direccion, vendedor, vendedor_id, geo_zone_id,
                         activo_ai, is_mock)
                    VALUES ($1,$2,$3,$4::core.dia_de_visita_enum,$5,$6,$7,$8,true,false)
                    RETURNING id
                    """,
                    row["razon_social"],
                    codigo,
                    1,
                    row["dia_de_visita"],
                    row.get("direccion") or "",
                    vrow["nombre"],
                    vendedor_id,
                    geo_zone_id,
                )
                cliente_id = await conn.fetchval(
                    f"""
                    INSERT INTO {SCHEMA}.clients
                        (phone_number, nombre, razon_social, lista_precios_id,
                         codigo, dia_de_visita, vendedor, pdv_id, activo_ai,
                         is_mock, lifecycle, origen_alta, is_primary, etiqueta)
                    VALUES (
                        $1,$2,$3,$4,$5,$6::core.dia_de_visita_enum,$7,$8,true,
                        false,'client','erp',true,$9
                    )
                    RETURNING id
                    """,
                    row["phone_number"],
                    row["nombre"],
                    row["razon_social"],
                    1,
                    codigo,
                    row["dia_de_visita"],
                    vrow["nombre"],
                    pdv_id,
                    row.get("categoria_pg") or None,
                )
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.vendedores_clientes
                        (vendedor_id, cliente_id, activo)
                    VALUES ($1,$2,true)
                    """,
                    vendedor_id,
                    cliente_id,
                )
                lat = float(row["lat"])
                lng = float(row["lng"])
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.client_locations
                        (client_id, source, latitude, longitude, location,
                         address_text, geocode_status, is_primary, created_by)
                    VALUES (
                        $1, 'backoffice', $2, $3,
                        extensions.ST_SetSRID(extensions.ST_MakePoint($3, $2), 4326),
                        $4, 'not_required', true, 'implementacion'
                    )
                    """,
                    cliente_id,
                    lat,
                    lng,
                    row.get("direccion") or "",
                )
            print(f"    clientes {i + 1}–{i + len(chunk)}")

        verify = await conn.fetchrow(
            f"""
            SELECT json_build_object(
              'productos', (SELECT COUNT(*) FROM {SCHEMA}.productos),
              'productos_catalogo', (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE en_catalogo AND NOT is_mock),
              'listas_publicas', (SELECT COUNT(*) FROM {SCHEMA}.listas_precios WHERE activa AND es_publica),
              'precios', (SELECT COUNT(*) FROM {SCHEMA}.precios_productos),
              'aliases', (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases),
              'vendedores', (SELECT COUNT(*) FROM {SCHEMA}.vendedores),
              'zonas', (SELECT COUNT(*) FROM {SCHEMA}.geo_zones),
              'zonas_con_principal', (SELECT COUNT(*) FROM {SCHEMA}.geo_zones WHERE vendedor_principal_id IS NOT NULL),
              'clients', (SELECT COUNT(*) FROM {SCHEMA}.clients),
              'clients_cartera', (SELECT COUNT(*) FROM {SCHEMA}.clients WHERE lifecycle = 'client' AND NOT is_mock),
              'pdv', (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta),
              'locs', (SELECT COUNT(*) FROM {SCHEMA}.client_locations),
              'vinculos', (SELECT COUNT(*) FROM {SCHEMA}.vendedores_clientes),
              'pedidos', (SELECT COUNT(*) FROM {SCHEMA}.pedidos),
              'mock_productos', (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE is_mock)
            ) AS x
            """
        )
        print(f"[VERIFY] {verify['x']}")
        x = verify["x"]
        if isinstance(x, str):
            import json
            x = json.loads(x)
        ok = (
            int(x["productos"]) == len(products)
            and int(x["precios"]) == len(products)
            and int(x["clients"]) == 239
            and int(x["zonas"]) == 5
            and int(x["vendedores"]) == 1
            and int(x["listas_publicas"]) == 1
            and int(x["mock_productos"]) == 0
        )
        if not ok:
            print("[FAIL] Conteos no coinciden con el CSV", file=sys.stderr)
            return 1
    finally:
        await conn.close()

    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize POST {vec_url} ({len(product_codes)} codes)...")
    try:
        resp = requests.post(vec_url, json=product_codes, timeout=180)
        print(f"[*] vectorize HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            print("[WARN] vectorize no devolvió 200")
    except Exception as e:
        print(f"[WARN] vectorize falló: {e}")
    print(f"[SUCCESS] carga producción {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cargar()))
