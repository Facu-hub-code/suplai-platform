#!/usr/bin/env python3
"""Carga datos ERP reales en schema curlo (reemplaza mock).

schema_name = curlo (confirmado por el implementador: confirmar carga).
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "curlo"  # confirmado dos veces: curlo
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
BATCH = 80
ITEM_BATCH = 200


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _load_envs() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT.parent / "backend-supabase" / ".env",
        ROOT / "backend" / ".env",
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


def read_csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


async def limpiar_mock(conn: asyncpg.Connection) -> None:
    print(f"[*] Limpiando mock previo en schema {SCHEMA}...")
    stmts = [
        f"DELETE FROM {SCHEMA}.field_task_events",
        f"DELETE FROM {SCHEMA}.field_tasks",
        f"DELETE FROM {SCHEMA}.field_point_ledger",
        f"DELETE FROM {SCHEMA}.field_objetivo_skus",
        f"DELETE FROM {SCHEMA}.field_objetivos",
        f"DELETE FROM {SCHEMA}.field_tournaments",
        f"DELETE FROM {SCHEMA}.items_pedido",
        f"DELETE FROM {SCHEMA}.pedidos",
        f"DELETE FROM {SCHEMA}.client_locations",
        f"DELETE FROM {SCHEMA}.vendedores_clientes",
        f"DELETE FROM {SCHEMA}.prospect_profiles",
        f"DELETE FROM {SCHEMA}.client_operating_profiles",
        f"DELETE FROM {SCHEMA}.cliente_producto_favorito",
        f"DELETE FROM {SCHEMA}.clientes_aliases",
        f"DELETE FROM {SCHEMA}.clientes_etiquetas",
        f"DELETE FROM {SCHEMA}.routes_clients",
        f"DELETE FROM {SCHEMA}.ia_tickets",
        f"DELETE FROM {SCHEMA}.conversations",
        f"DELETE FROM {SCHEMA}.clients",
        f"DELETE FROM {SCHEMA}.puntos_venta",
        f"DELETE FROM {SCHEMA}.precios_productos",
        f"DELETE FROM {SCHEMA}.productos_aliases",
        f"DELETE FROM {SCHEMA}.product_categories",
        f"DELETE FROM {SCHEMA}.product_tags",
        f"DELETE FROM {SCHEMA}.promocion_grupo_productos",
        f"DELETE FROM {SCHEMA}.promociones_semanales",
        f"DELETE FROM {SCHEMA}.productos",
        f"DELETE FROM {SCHEMA}.vendedor_geo_zones",
        f"DELETE FROM {SCHEMA}.geo_zones",
        f"DELETE FROM {SCHEMA}.vendedores",
        f"DELETE FROM {SCHEMA}.listas_precios WHERE id = 4",
    ]
    for sql in stmts:
        try:
            result = await conn.execute(sql)
            print(f"    {sql.split('FROM', 1)[-1].strip() if 'FROM' in sql else sql}: {result}")
        except asyncpg.PostgresError as exc:
            print(f"    WARN {sql}: {exc}")


async def cargar() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] tenant destino: {SCHEMA} (CURLO — reemplazo mock por ERP)")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    productos = read_csv("phase-01-productos.csv")
    clientes = read_csv("phase-04-clientes.csv")
    vendedores = read_csv("phase-04-vendedores.csv")
    pedidos = read_csv("phase-06-pedidos.csv")
    items = read_csv("phase-06-items-pedido.csv")
    listas = read_csv("phase-01-listas-precios.csv")
    print(
        f"[*] CSV productos={len(productos)} clientes={len(clientes)} "
        f"vendedores={len(vendedores)} pedidos={len(pedidos)} items={len(items)}"
    )

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        await conn.execute(f"SET search_path TO {SCHEMA}, core, public")

        before = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.clients) AS clients,
              (SELECT COUNT(*) FROM {SCHEMA}.pedidos) AS pedidos
            """
        )
        print(f"[*] antes: {dict(before)}")

        await limpiar_mock(conn)

        for lp in listas:
            lid = int(lp["lista_precios_id"])
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.listas_precios
                  (id, nombre, descripcion, activa, es_publica, is_mock, erp_list_id, erp_connector, created_at, updated_at)
                OVERRIDING SYSTEM VALUE
                VALUES ($1, $2, $3, true, true, false, $4, 'httpshare', now(), now())
                ON CONFLICT (id) DO UPDATE SET
                  nombre = EXCLUDED.nombre,
                  descripcion = EXCLUDED.descripcion,
                  activa = true,
                  es_publica = true,
                  is_mock = false,
                  erp_list_id = EXCLUDED.erp_list_id,
                  erp_connector = EXCLUDED.erp_connector,
                  updated_at = now()
                """,
                lid,
                lp["nombre"],
                f"Lista ERP {lp['nombre']}",
                str(lid),
            )
        await conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{SCHEMA}.listas_precios', 'id'), 3, true)"
        )
        print("[*] listas 1–3 upsert OK")

        products_data = []
        aliases_data = []
        product_codes: list[str] = []
        seen_alias: set[tuple[str, str]] = set()
        for p in productos:
            code = p["product_code"].strip()
            product_codes.append(code)
            umv = (p.get("unidad_minima_de_venta") or "unidad").strip() or "unidad"
            umv_tipo = (p.get("umv_tipo") or "unidad").strip() or "unidad"
            if umv_tipo not in ("unidad", "display"):
                umv_tipo = "unidad"
            qty_min = int(float(p["cantidad_minima_de_venta"])) if p.get("cantidad_minima_de_venta") else 1
            products_data.append(
                (
                    code,
                    p["nombre"],
                    p.get("descripcion") or None,
                    (p.get("image_url") or "").strip() or None,
                    int(float(p["stock"])) if p.get("stock") not in (None, "") else 0,
                    int(float(p["unidades_por_bulto"])) if p.get("unidades_por_bulto") else 1,
                    umv,
                    umv_tipo,
                    float(p["rotacion_index"]) if p.get("rotacion_index") else 0.1,
                    float(p["mental_priority"]) if p.get("mental_priority") else 0.0,
                    truthy(p.get("en_catalogo") or "true"),
                    False,
                    qty_min,
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

        print(f"[*] INSERT {SCHEMA}.productos ({len(products_data)})")
        for i in range(0, len(products_data), BATCH):
            chunk = products_data[i : i + BATCH]
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.productos (
                    product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                    unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority,
                    en_catalogo, is_mock, cantidad_minima_de_venta, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, now(), now())
                """,
                chunk,
            )
            print(f"    productos {i + 1}–{i + len(chunk)}")

        print(f"[*] INSERT {SCHEMA}.productos_aliases ({len(aliases_data)})")
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

        prices_data = []
        for lid in (1, 2, 3):
            path = OUT / f"phase-01-lista-precios-{lid}.csv"
            if not path.exists():
                continue
            for row in csv.DictReader(path.open(encoding="utf-8")):
                prices_data.append(
                    (row["product_code"].strip(), lid, float(row["precio_unidad"]), False)
                )
        print(f"[*] INSERT {SCHEMA}.precios_productos ({len(prices_data)})")
        for i in range(0, len(prices_data), BATCH):
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.precios_productos (
                    product_code, lista_precios_id, precio_unidad, is_mock
                ) VALUES ($1,$2,$3,$4)
                """,
                prices_data[i : i + BATCH],
            )

        vend_id_by_codigo: dict[int, int] = {}
        print(f"[*] INSERT {SCHEMA}.vendedores ({len(vendedores)})")
        for row in vendedores:
            codigo = int(row["vendedor_codigo"])
            telefono = (row.get("telefono") or "").strip() or f"erp-{codigo}"
            vid = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.vendedores
                  (nombre, telefono, email, zona, codigo_ruta, activo, is_mock)
                VALUES ($1, $2, NULLIF($3,''), NULL, $4, true, false)
                RETURNING id
                """,
                row["nombre"].strip(),
                telefono,
                (row.get("email") or "").strip(),
                str(codigo),
            )
            vend_id_by_codigo[codigo] = int(vid)
            print(f"    vendedor {row['nombre']} erp={codigo} → id={vid}")

        seen_phones: set[str] = set()
        client_id_by_codigo: dict[int, int] = {}
        print(f"[*] INSERT {SCHEMA}.puntos_venta + clients ({len(clientes)})")
        for i, row in enumerate(clientes, start=1):
            codigo = int(row["cliente_codigo"])
            lista_id = int(row["lista_precios_id"] or 1)
            if lista_id not in (1, 2, 3):
                lista_id = 1
            vend_codigo = row.get("vendedor_codigo") or ""
            vend_db = vend_id_by_codigo.get(int(vend_codigo)) if str(vend_codigo).strip() else None
            vend_name = (row.get("vendedor_nombre") or "").strip() or None
            phone_real = (row.get("phone_number") or "").strip()
            if phone_real and phone_real not in seen_phones:
                phone = phone_real
            else:
                phone = f"erp-{codigo}"
            seen_phones.add(phone)
            razon = row["razon_social"].strip()
            nombre = (row.get("nombre") or razon).strip()
            activo_ai = codigo != 1 and phone_real != "" and not phone.startswith("erp-")
            pdv_id = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.puntos_venta (
                    razon_social, codigo, lista_precios_id, direccion, email,
                    vendedor, vendedor_id, activo_ai, is_mock, cuit
                ) VALUES ($1,$2,$3,NULLIF($4,''),NULLIF($5,''),$6,$7,$8,false,NULLIF($9,''))
                RETURNING id
                """,
                razon,
                codigo,
                lista_id,
                (row.get("direccion") or "").strip(),
                (row.get("email") or "").strip(),
                vend_name,
                vend_db,
                activo_ai,
                (row.get("cuit") or "").strip(),
            )
            cid = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.clients (
                    phone_number, nombre, razon_social, lista_precios_id, codigo,
                    activo_ai, vendedor, is_primary, is_mock, partner_erp_id,
                    pdv_id, email, cuit, lifecycle, origen_alta, metadata
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,true,false,$8,$9,NULLIF($10,''),NULLIF($11,''),
                    'client','erp',$12::jsonb
                )
                RETURNING id
                """,
                phone,
                nombre,
                razon,
                lista_id,
                codigo,
                activo_ai,
                vend_name,
                codigo,
                pdv_id,
                (row.get("email") or "").strip(),
                (row.get("cuit") or "").strip(),
                json.dumps(
                    {
                        "origen": "erp_httpshare",
                        "localidad": row.get("localidad") or "",
                        "provincia": row.get("provincia") or "",
                        "direccion": row.get("direccion") or "",
                    },
                    ensure_ascii=False,
                ),
            )
            client_id_by_codigo[codigo] = int(cid)
            if vend_db:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.vendedores_clientes (vendedor_id, cliente_id, activo)
                    VALUES ($1,$2,true)
                    """,
                    vend_db,
                    cid,
                )
            if i % 200 == 0:
                print(f"    clientes {i}/{len(clientes)}")
        print(f"    clientes done {len(client_id_by_codigo)}")

        items_by_ref: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            items_by_ref[str(it["pedido_ref"])].append(it)
        ped_by_ref = {str(p["pedido_ref"]): p for p in pedidos}

        print(f"[*] INSERT {SCHEMA}.pedidos ({len(pedidos)})")
        order_id_by_ref: dict[str, int] = {}
        skipped_cli = 0
        for i in range(0, len(pedidos), BATCH):
            batch = pedidos[i : i + BATCH]
            cliente_ids = []
            fechas = []
            items_json = []
            totals = []
            estados = []
            notas = []
            refs = []
            keep_rows = []
            for row in batch:
                codigo = int(row["cliente_codigo"])
                cid = client_id_by_codigo.get(codigo)
                if not cid:
                    skipped_cli += 1
                    continue
                ref = str(row["pedido_ref"])
                keep_rows.append(row)
                cliente_ids.append(cid)
                fechas.append(datetime.fromisoformat(row["fecha"]))
                lines = items_by_ref.get(ref, [])
                items_json.append(
                    json.dumps(
                        [
                            {
                                "product_code": ln["product_code"],
                                "nombre": ln.get("nombre") or "",
                                "cantidad_solicitada": float(ln["cantidad_solicitada"] or 0),
                                "precio_unitario": float(ln["precio_unitario"] or 0),
                            }
                            for ln in lines
                        ],
                        ensure_ascii=False,
                    )
                )
                totals.append(Decimal(str(row["total"] or "0")))
                estados.append(row["estado"])
                notas.append(row.get("notas") or "")
                refs.append(ref)
            if not keep_rows:
                continue
            returned = await conn.fetch(
                f"""
                INSERT INTO {SCHEMA}.pedidos (
                    cliente_id, fecha, items, total, estado, notas,
                    erp_reference_id, is_mock, origen, updated_at, order_reference
                )
                SELECT cliente_id, fecha, items_text::jsonb, total, estado,
                       notas, erp_ref, false, 'erp', now(), order_ref
                FROM UNNEST(
                    $1::integer[], $2::timestamp[], $3::text[],
                    $4::numeric[], $5::text[], $6::text[],
                    $7::text[], $8::text[]
                ) AS x(cliente_id,fecha,items_text,total,estado,notas,erp_ref,order_ref)
                RETURNING id, order_reference
                """,
                cliente_ids,
                fechas,
                items_json,
                totals,
                estados,
                notas,
                refs,
                refs,
            )
            for r in returned:
                order_id_by_ref[str(r["order_reference"])] = int(r["id"])
            print(f"    pedidos {i + 1}–{i + len(batch)} (ok {len(returned)})")
        print(f"    pedidos insertados={len(order_id_by_ref)} skip_sin_cliente={skipped_cli}")

        item_rows = []
        missing_order = 0
        missing_client = 0
        for it in items:
            ref = str(it["pedido_ref"])
            pid = order_id_by_ref.get(ref)
            if not pid:
                missing_order += 1
                continue
            # client_id en items_pedido es varchar
            ped = ped_by_ref.get(ref)
            codigo = int(ped["cliente_codigo"]) if ped else 0
            cid = client_id_by_codigo.get(codigo)
            if not cid:
                missing_client += 1
                continue
            item_rows.append(
                (
                    str(cid),
                    it["product_code"].strip(),
                    Decimal(str(it["precio_unitario"] or "0")),
                    datetime.fromisoformat(ped["fecha"]).date() if ped else None,
                    (it.get("notas") or "") or None,
                    (it.get("nombre") or "") or None,
                    Decimal(str(it["cantidad_solicitada"] or "0")),
                    pid,
                    False,
                )
            )
        print(f"[*] INSERT {SCHEMA}.items_pedido ({len(item_rows)}) missing_order={missing_order} missing_client={missing_client}")
        for i in range(0, len(item_rows), ITEM_BATCH):
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.items_pedido (
                    client_id, product_code, precio_unitario, fecha_pedido, notas,
                    nombre, cantidad_solicitada, pedido_id, is_mock
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                """,
                item_rows[i : i + ITEM_BATCH],
            )
            if (i // ITEM_BATCH) % 10 == 0:
                print(f"    items {i + 1}–{min(i + ITEM_BATCH, len(item_rows))}")

        verify = await conn.fetchrow(
            f"""
            SELECT json_build_object(
              'productos', (SELECT COUNT(*) FROM {SCHEMA}.productos),
              'en_catalogo', (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE en_catalogo),
              'listas', (SELECT COUNT(*) FROM {SCHEMA}.listas_precios),
              'precios', (SELECT COUNT(*) FROM {SCHEMA}.precios_productos),
              'aliases', (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases),
              'clients', (SELECT COUNT(*) FROM {SCHEMA}.clients),
              'clients_wa', (SELECT COUNT(*) FROM {SCHEMA}.clients WHERE phone_number ~ '^549[0-9]{8,12}$'),
              'clients_mock', (SELECT COUNT(*) FROM {SCHEMA}.clients WHERE is_mock),
              'pdv', (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta),
              'vendedores', (SELECT COUNT(*) FROM {SCHEMA}.vendedores),
              'pedidos', (SELECT COUNT(*) FROM {SCHEMA}.pedidos WHERE deleted_at IS NULL),
              'pedidos_mock', (SELECT COUNT(*) FROM {SCHEMA}.pedidos WHERE is_mock),
              'abiertos', (SELECT COUNT(*) FROM {SCHEMA}.pedidos WHERE estado = 'pendiente'),
              'items', (SELECT COUNT(*) FROM {SCHEMA}.items_pedido)
            ) AS v
            """
        )
        print(f"[VERIFY] {verify['v']}")
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
    except Exception as exc:
        print(f"[WARN] vectorize falló: {exc}")
    print(f"[SUCCESS] carga ERP {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cargar()))
