#!/usr/bin/env python3
"""
Detecta y opcionalmente carga SKUs + clientes del Excel de ventas que no están en catálogo/cartera.

Lee ventas mar–jun (por defecto), genera CSV preview y con --apply inserta en el_gigante.
Omite EGRESO 10002. Productos reales is_mock=false.

Uso:
  python scripts/el_gigante_ventas/00_cargar_faltantes.py
  python scripts/el_gigante_ventas/00_cargar_faltantes.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import asyncpg

from _common import (
    DEFAULT_INPUT_DIR,
    DEFAULT_SCHEMA,
    PLACEHOLDER_IMAGE,
    SKIP_PRODUCT_LOAD_CODES,
    VentaRow,
    add_mes_arg,
    client_code_raw,
    configure_stdout,
    db_url,
    fetch_db_codes,
    load_catalog_product_codes,
    load_client_codes_from_outputs,
    norm_match_key,
    parse_meses,
    period_slug,
    pooler_url,
    read_ventas_meses,
    resolve_vendedor_canonico,
    resolve_zone_name_from_ruta,
    tenant_outputs,
    to_decimal,
    write_csv,
    write_json,
)


def _norm_key(text: str) -> str:
    return norm_match_key(text)


def _alias_norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in s if c.isalnum())


def aggregate_missing_products(rows: list[VentaRow], catalog: set[str]) -> list[dict]:
    by_code: dict[str, dict] = {}
    for row in rows:
        if not row.cod_art or row.cod_art in catalog:
            continue
        if row.cod_art in SKIP_PRODUCT_LOAD_CODES:
            continue
        bucket = by_code.setdefault(
            row.cod_art,
            {
                "product_code": row.cod_art,
                "articulo": row.articulo,
                "grupo": Counter(),
                "marca": Counter(),
                "proveedor": Counter(),
                "cantidad": 0.0,
                "ventas_neto": Decimal("0"),
                "lineas": 0,
            },
        )
        if row.articulo:
            bucket["articulo"] = row.articulo
        if row.grupo:
            bucket["grupo"][row.grupo] += 1
        if row.marca:
            bucket["marca"][row.marca] += 1
        if row.proveedor:
            bucket["proveedor"][row.proveedor] += 1
        if row.cant_vendida > 0:
            bucket["cantidad"] += row.cant_vendida
            bucket["ventas_neto"] += row.total_ventas_neto
            bucket["lineas"] += 1

    out = []
    for code, data in sorted(by_code.items()):
        grupo = data["grupo"].most_common(1)[0][0] if data["grupo"] else ""
        marca = data["marca"].most_common(1)[0][0] if data["marca"] else ""
        proveedor = data["proveedor"].most_common(1)[0][0] if data["proveedor"] else ""
        qty = data["cantidad"]
        ventas = data["ventas_neto"]
        precio = (ventas / Decimal(str(qty))).quantize(Decimal("0.01")) if qty > 0 else Decimal("1")
        out.append(
            {
                "product_code": code,
                "nombre": data["articulo"] or code,
                "grupo": grupo,
                "marca": marca,
                "proveedor": proveedor,
                "precio_lista_1": str(precio),
                "lineas_venta": data["lineas"],
                "cantidad_vendida": round(qty, 2),
                "accion": "insertar",
            }
        )
    return out


def aggregate_missing_clients(rows: list[VentaRow], known_codes: set[str]) -> list[dict]:
    by_code: dict[str, dict] = {}
    for row in rows:
        code = row.ccliente
        if not code or code in known_codes:
            continue
        bucket = by_code.setdefault(
            code,
            {
                "codigo": code,
                "cliente": row.cliente,
                "vendedor": Counter(),
                "ruta": Counter(),
                "lineas": 0,
            },
        )
        if row.cliente:
            bucket["cliente"] = row.cliente
        if row.vendedor:
            bucket["vendedor"][row.vendedor] += 1
        if row.ruta:
            bucket["ruta"][row.ruta] += 1
        bucket["lineas"] += 1

    out = []
    for code, data in sorted(by_code.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        vendedor = data["vendedor"].most_common(1)[0][0] if data["vendedor"] else ""
        ruta = data["ruta"].most_common(1)[0][0] if data["ruta"] else ""
        out.append(
            {
                "codigo": code,
                "nombre": data["cliente"] or f"Cliente ERP {code}",
                "razon_social": data["cliente"] or f"Cliente ERP {code}",
                "vendedor": vendedor,
                "ruta": ruta,
                "lineas_venta": data["lineas"],
                "accion": "insertar",
            }
        )
    return out


async def apply_faltantes(schema: str, products: list[dict], clients: list[dict]) -> dict:
    url = db_url()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")

    conn = await asyncpg.connect(url, statement_cache_size=0)
    stats = {
        "productos_insertados": 0,
        "precios_insertados": 0,
        "aliases_insertados": 0,
        "clientes_insertados": 0,
        "pdv_insertados": 0,
        "sin_vendedor": 0,
        "sin_zona": 0,
    }
    try:
        await conn.execute(f"SET search_path TO {schema}, core, public, extensions")

        existing_products = {
            r["product_code"]
            for r in await conn.fetch("SELECT product_code FROM productos")
        }
        existing_clients = {
            client_code_raw(r["codigo"])
            for r in await conn.fetch("SELECT codigo FROM clients WHERE codigo IS NOT NULL")
        }
        existing_phones = {
            r["phone_number"]
            for r in await conn.fetch("SELECT phone_number FROM clients")
        }

        for row in products:
            code = row["product_code"]
            if code in existing_products:
                continue
            nombre = row["nombre"] or code
            precio = to_decimal(row.get("precio_lista_1") or "1")
            await conn.execute(
                """
                INSERT INTO productos (
                    product_code, nombre, descripcion, image_url, stock,
                    unidades_por_bulto, unidad_minima_de_venta, umv_tipo,
                    rotacion_index, mental_priority, en_catalogo, is_mock,
                    cantidad_minima_de_venta, created_at, updated_at
                ) VALUES (
                    $1, $2, $2, $3, 0,
                    1, '1', 'unidad',
                    0.5, 0.5, true, false,
                    1, NOW(), NOW()
                )
                """,
                code,
                nombre,
                PLACEHOLDER_IMAGE,
            )
            stats["productos_insertados"] += 1
            await conn.execute(
                """
                INSERT INTO precios_productos (product_code, lista_precios_id, precio_unidad, is_mock)
                VALUES ($1, 1, $2, false)
                ON CONFLICT (product_code, lista_precios_id) DO UPDATE
                SET precio_unidad = EXCLUDED.precio_unidad
                """,
                code,
                precio,
            )
            stats["precios_insertados"] += 1
            alias_norm = _alias_norm(nombre)
            if alias_norm:
                await conn.execute(
                    """
                    INSERT INTO productos_aliases (product_code, alias_raw, alias_norm, weight, created_at, updated_at)
                    VALUES ($1, $2, $3, 1, NOW(), NOW())
                    ON CONFLICT (product_code, alias_norm) DO NOTHING
                    """,
                    code,
                    nombre,
                    alias_norm,
                )
                stats["aliases_insertados"] += 1
            existing_products.add(code)

        vendedores = {
            _norm_key(r["nombre"]): (int(r["id"]), r["nombre"])
            for r in await conn.fetch(
                "SELECT id, nombre FROM vendedores WHERE COALESCE(is_mock,false)=false"
            )
        }
        zone_rows = await conn.fetch(
            """
            SELECT gz.id, gz.name, gz.vendedor_principal_id
            FROM geo_zones gz
            WHERE COALESCE(gz.is_mock,false)=false
            """
        )
        zone_by_name = {_norm_key(zr["name"]): (int(zr["id"]), int(zr["vendedor_principal_id"]), zr["name"]) for zr in zone_rows}
        zones_by_vendedor: dict[int, list[tuple[int, str, str]]] = defaultdict(list)
        for zr in zone_rows:
            vid = zr["vendedor_principal_id"]
            if vid:
                zones_by_vendedor[int(vid)].append((int(zr["id"]), zr["name"], _norm_key(zr["name"])))

        def resolve_vendedor_zone(vendedor_excel: str, ruta: str) -> tuple[int, str, int] | None:
            zone_target = resolve_zone_name_from_ruta(ruta)
            if zone_target:
                hit = zone_by_name.get(_norm_key(zone_target))
                if hit:
                    zid, vid, _ = hit
                    vendedor_name = next((n for i, n in vendedores.values() if i == vid), resolve_vendedor_canonico(vendedor_excel))
                    return vid, vendedor_name, zid

            canon = resolve_vendedor_canonico(vendedor_excel)
            if not canon:
                return None
            vmatch = vendedores.get(_norm_key(canon))
            if not vmatch:
                return None
            vendedor_id, vendedor_name = vmatch
            ruta_key = _norm_key(ruta)
            candidates = zones_by_vendedor.get(vendedor_id, [])
            for zid, _name, zkey in candidates:
                if ruta_key and (ruta_key in zkey or zkey in ruta_key):
                    return vendedor_id, vendedor_name, zid
            for zid, _name, zkey in candidates:
                ruta_tokens = set(ruta_key.split())
                zone_tokens = set(zkey.split())
                if ruta_tokens & zone_tokens:
                    return vendedor_id, vendedor_name, zid
            if candidates:
                return vendedor_id, vendedor_name, candidates[0][0]
            return None

        for row in clients:
            code = row["codigo"]
            if code in existing_clients:
                continue
            resolved = resolve_vendedor_zone(row.get("vendedor") or "", row.get("ruta") or "")
            if not resolved:
                stats["sin_vendedor"] += 1
                continue
            vendedor_id, vendedor_name, zid = resolved

            try:
                codigo_num = float(code)
            except ValueError:
                continue

            phone = f"5493708{int(codigo_num):07d}"[-13:]
            while phone in existing_phones:
                phone = f"5493709{int(codigo_num):07d}"[-13:]
                codigo_num += 0.1

            nombre = row.get("nombre") or f"Cliente ERP {code}"
            razon = row.get("razon_social") or nombre

            pdv_id = await conn.fetchval(
                """
                INSERT INTO puntos_venta (
                  razon_social, codigo, lista_precios_id, dia_de_visita, dia_de_entrega,
                  direccion, vendedor_id, geo_zone_id, geo_zone_asignacion, is_mock)
                VALUES (
                  $1, $2, 1,
                  'lunes'::core.dia_de_visita_enum,
                  'martes'::core.dia_de_entrega_enum,
                  $3, $4, $5, 'manual', false
                )
                RETURNING id
                """,
                razon,
                codigo_num,
                f"Ruta ventas ERP — {row.get('ruta') or ''}".strip(),
                vendedor_id,
                zid,
            )
            stats["pdv_insertados"] += 1

            cliente_id = await conn.fetchval(
                """
                INSERT INTO clients (
                  phone_number, nombre, razon_social, lista_precios_id, codigo,
                  dia_de_visita, dia_de_entrega, direccion, vendedor,
                  pdv_id, is_primary, activo_ai, is_mock, partner_erp_id)
                VALUES (
                  $1, $2, $3, 1, $4,
                  'lunes'::core.dia_de_visita_enum,
                  'martes'::core.dia_de_entrega_enum,
                  $5, $6,
                  $7, true, true, false, $8
                )
                RETURNING id
                """,
                phone,
                nombre,
                razon,
                codigo_num,
                f"Ruta ventas ERP — {row.get('ruta') or ''}".strip(),
                vendedor_name,
                pdv_id,
                int(codigo_num),
            )
            await conn.execute(
                """
                INSERT INTO vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true
                """,
                vendedor_id,
                cliente_id,
            )
            existing_clients.add(code)
            existing_phones.add(phone)
            stats["clientes_insertados"] += 1

    finally:
        await conn.close()
    return stats


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Cargar SKUs y clientes faltantes el_gigante")
    parser.add_argument("--esquema", default=DEFAULT_SCHEMA)
    add_mes_arg(parser)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="INSERT productos/clientes en BD")
    args = parser.parse_args()

    meses = parse_meses(args.mes, todos=args.todos)
    periodo = period_slug(meses)
    rows = read_ventas_meses(meses, args.input_dir)

    catalog_csv = load_catalog_product_codes(args.esquema)
    clients_csv = load_client_codes_from_outputs(args.esquema)

    db_products, db_clients = asyncio.run(fetch_db_codes(args.esquema))
    catalog = catalog_csv | db_products
    known_clients = clients_csv | db_clients

    missing_products = aggregate_missing_products(rows, catalog)
    missing_clients = aggregate_missing_clients(rows, known_clients)

    out_dir = tenant_outputs(args.esquema)
    prod_csv = out_dir / f"ventas-{periodo}-productos-faltantes-preview.csv"
    cli_csv = out_dir / f"ventas-{periodo}-clientes-faltantes-preview.csv"
    summary_path = out_dir / f"ventas-{periodo}-faltantes-resumen.json"

    write_csv(
        prod_csv,
        missing_products,
        [
            "product_code",
            "nombre",
            "grupo",
            "marca",
            "proveedor",
            "precio_lista_1",
            "lineas_venta",
            "cantidad_vendida",
            "accion",
        ],
    )
    write_csv(
        cli_csv,
        missing_clients,
        ["codigo", "nombre", "razon_social", "vendedor", "ruta", "lineas_venta", "accion"],
    )

    summary = {
        "schema": args.esquema,
        "periodo": periodo,
        "meses": meses,
        "filas_excel": len(rows),
        "productos_faltantes": len(missing_products),
        "clientes_faltantes": len(missing_clients),
        "omitidos_carga_producto": sorted(SKIP_PRODUCT_LOAD_CODES),
        "csv_productos": str(prod_csv),
        "csv_clientes": str(cli_csv),
        "modo": "apply" if args.apply else "dry-run",
    }
    write_json(summary_path, summary)

    print(f"[*] Periodo: {periodo} ({', '.join(meses)}) — {len(rows)} filas Excel")
    print(f"[*] Productos faltantes: {len(missing_products)} | Clientes faltantes: {len(missing_clients)}")
    print(f"[*] Preview productos: {prod_csv}")
    print(f"[*] Preview clientes: {cli_csv}")
    print(f"[*] Resumen: {summary_path}")

    if args.apply:
        print(f"[!] Aplicando faltantes en schema {args.esquema}…")
        stats = asyncio.run(apply_faltantes(args.esquema, missing_products, missing_clients))
        print(
            f"[OK] Productos: {stats['productos_insertados']} | Precios: {stats['precios_insertados']} | "
            f"Clientes: {stats['clientes_insertados']} | PDV: {stats['pdv_insertados']}"
        )
        if stats["sin_vendedor"] or stats["sin_zona"]:
            print(
                f"[WARN] Omitidos — sin vendedor: {stats['sin_vendedor']} | sin zona: {stats['sin_zona']}"
            )
    else:
        print("[*] Dry-run. Revisá CSVs y corré con --apply.")


if __name__ == "__main__":
    main()
