#!/usr/bin/env python3
"""Carga Litoral en schema dimer y crea la plantilla Meta dimer_litoral_contacto_v1.

Pooler 6543, statement_cache_size=0, una conexión. No borra clientes ni a Cata.
"""
from __future__ import annotations

import csv
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import asyncpg
import certifi
from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV = ROOT.parent / "backend-supabase" / ".env"
OUT = Path(__file__).resolve().parents[1] / "outputs"
SCHEMA = "dimer"
TENANT_ID = "02a0c4e0-8ac7-4bf1-aee9-19b44a14f66a"
TEMPLATE_NAME = "dimer_litoral_contacto_v1"
GRAPH = "https://graph.facebook.com/v21.0"
CTX = ssl.create_default_context(cafile=certifi.where())
BATCH = 80

load_dotenv(BACKEND_ENV)

TEMPLATE_BODY = (
    "Hola, te escribe el WhatsApp de Dimer. Para pedidos y consultas de tu zona, "
    "tu vendedor/a es {{1}}. Si no lo encontrás, tu jefe de ventas es Francisco Díaz "
    "al +56 9 6191 6961. Así te atendemos más rápido."
)
TEMPLATE_EXAMPLE = [["Gustavo López al +56 9 6403 7193"]]


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def fmt_cl_mobile(digits: str) -> str:
    d = "".join(c for c in digits if c.isdigit())
    if d.startswith("56") and len(d) >= 11:
        rest = d[2:]
        if rest.startswith("9") and len(rest) >= 9:
            return f"+56 9 {rest[1:5]} {rest[5:9]}"
    return f"+{d}" if d else ""


def vendedor_label(nombre: str, telefono: str) -> str:
    pretty = fmt_cl_mobile(telefono)
    return f"{nombre} al {pretty}" if pretty else nombre


def chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def graph_post_json(url: str, token: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed


def load_destinatarios() -> list[dict]:
    cartera_by_key: dict[str, dict] = {}
    with (OUT / "litoral-cartera.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = (row.get("mobile_key") or "").strip()
            if k and k not in cartera_by_key:
                cartera_by_key[k] = row
    dest = []
    with (OUT / "litoral-destinatarios-whatsapp.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = (row.get("mobile_key") or "").strip()
            extra = cartera_by_key.get(k, {})
            row["direccion"] = extra.get("direccion") or ""
            row["dias_visita"] = extra.get("dias_visita") or ""
            dest.append(row)
    return dest


def load_vendedores_csv() -> list[dict]:
    with (OUT / "litoral-vendedores.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def ensure_etiqueta(conn: asyncpg.Connection, name: str) -> int:
    row = await conn.fetchrow("SELECT id FROM dimer.etiquetas WHERE name = $1 LIMIT 1", name)
    if row:
        return int(row["id"])
    return int(await conn.fetchval("INSERT INTO dimer.etiquetas (name) VALUES ($1) RETURNING id", name))


async def ensure_grupo(conn: asyncpg.Connection, nombre: str, etiqueta_id: int, vendedor_id: int | None) -> int:
    row = await conn.fetchrow("SELECT id FROM dimer.grupos WHERE nombre = $1 LIMIT 1", nombre)
    if row:
        await conn.execute(
            """
            UPDATE dimer.grupos
            SET etiqueta_ids = ARRAY[$2]::int[], vendedor_id = $3, activo_ai = true
            WHERE id = $1
            """,
            int(row["id"]),
            etiqueta_id,
            vendedor_id,
        )
        return int(row["id"])
    return int(
        await conn.fetchval(
            """
            INSERT INTO dimer.grupos (nombre, activo_ai, etiqueta_ids, vendedor_id)
            VALUES ($1, true, ARRAY[$2]::int[], $3)
            RETURNING id
            """,
            nombre,
            etiqueta_id,
            vendedor_id,
        )
    )


async def load_db(conn: asyncpg.Connection) -> dict:
    print("[*] Tenant confirmado: dimer", flush=True)
    await conn.execute("SET search_path TO dimer, core, public, extensions")
    vendedores_src = load_vendedores_csv()
    dest = load_destinatarios()
    print(f"[*] destinatarios WA {len(dest)}")

    vend_ids: dict[str, int] = {}
    async with conn.transaction():
        for v in vendedores_src:
            row = await conn.fetchrow(
                """
                INSERT INTO dimer.vendedores (nombre, telefono, zona, codigo_ruta, activo, is_mock)
                VALUES ($1, $2, $3, $4, true, false)
                ON CONFLICT (telefono) DO UPDATE SET
                    nombre = EXCLUDED.nombre,
                    zona = EXCLUDED.zona,
                    codigo_ruta = EXCLUDED.codigo_ruta,
                    activo = true,
                    is_mock = false,
                    updated_at = now()
                RETURNING id, codigo_ruta
                """,
                v["nombre"],
                v["telefono"],
                v["territorio"],
                v["codigo_ruta"],
            )
            vend_ids[row["codigo_ruta"]] = int(row["id"])
            print(f"    vendedor {v['nombre']} id={row['id']} ruta={v['codigo_ruta']}")

        etq_litoral = await ensure_etiqueta(conn, "Litoral")
        await ensure_grupo(conn, "Litoral", etq_litoral, None)
        etq_by_ruta: dict[str, int] = {}
        for v in vendedores_src:
            if v["rol"] != "vendedor":
                continue
            etq_id = await ensure_etiqueta(conn, f"Litoral - {v['territorio']}")
            etq_by_ruta[v["codigo_ruta"]] = etq_id
            await ensure_grupo(
                conn,
                f"Litoral - {v['territorio']}",
                etq_id,
                vend_ids[v["codigo_ruta"]],
            )

        existing = [r for r in dest if (r.get("client_id") or "").strip()]
        to_create = [r for r in dest if not (r.get("client_id") or "").strip()]
        print(f"[*] asignar existentes {len(existing)} · crear {len(to_create)}")

        updated = 0
        for r in existing:
            cid = int(r["client_id"])
            ruta = r["codigo_ruta"]
            vid = vend_ids[ruta]
            label = vendedor_label(r["vendedor_nombre"], r["vendedor_telefono"])
            meta = json.dumps(
                {
                    "origen": "litoral_7_vendedores",
                    "codigo_ruta": ruta,
                    "jefe_zonal": r["jefe_zonal_nombre"],
                    "jefe_zonal_telefono": r["jefe_zonal_telefono"],
                },
                ensure_ascii=False,
            )
            await conn.execute(
                """
                UPDATE dimer.clients
                SET vendedor = $2,
                    cuit = COALESCE(NULLIF(btrim(cuit), ''), $3),
                    direccion = COALESCE(NULLIF(btrim(direccion), ''), NULLIF($4, '')),
                    metadata = COALESCE(metadata, '{}'::jsonb) || $5::jsonb,
                    updated_at = now()
                WHERE id = $1
                """,
                cid,
                label,
                r["rut"],
                r.get("direccion") or "",
                meta,
            )
            await conn.execute(
                "UPDATE dimer.vendedores_clientes SET activo = false, updated_at = now() WHERE cliente_id = $1 AND vendedor_id <> $2",
                cid,
                vid,
            )
            await conn.execute(
                """
                INSERT INTO dimer.vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true, updated_at = now()
                """,
                vid,
                cid,
            )
            await conn.execute(
                "INSERT INTO dimer.clientes_etiquetas (client_id, etiqueta_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                cid,
                etq_litoral,
            )
            await conn.execute(
                "INSERT INTO dimer.clientes_etiquetas (client_id, etiqueta_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                cid,
                etq_by_ruta[ruta],
            )
            updated += 1
        print(f"[*] existentes actualizados {updated}")

        created = 0
        skipped = 0
        for batch in chunks(to_create, BATCH):
            phones = [r["telefono"] for r in batch]
            already = {
                str(r["phone_number"]): int(r["id"])
                for r in await conn.fetch(
                    "SELECT id, phone_number FROM dimer.clients WHERE phone_number = ANY($1::varchar[])",
                    phones,
                )
            }
            reuse_rows = []
            new_rows = []
            for r in batch:
                if r["telefono"] in already:
                    r = dict(r)
                    r["_cid"] = already[r["telefono"]]
                    reuse_rows.append(r)
                    skipped += 1
                else:
                    new_rows.append(r)

            new_ids: list[int] = []
            if new_rows:
                razons = [(r["razon_social"] or "Cliente Litoral").strip()[:500] for r in new_rows]
                cuits = [r["rut"] or None for r in new_rows]
                dirs = [(r.get("direccion") or "").strip()[:500] or None for r in new_rows]
                labels = [vendedor_label(r["vendedor_nombre"], r["vendedor_telefono"]) for r in new_rows]
                vids = [vend_ids[r["codigo_ruta"]] for r in new_rows]
                metas = [
                    json.dumps(
                        {
                            "origen": "litoral_7_vendedores",
                            "codigo_ruta": r["codigo_ruta"],
                            "jefe_zonal": r["jefe_zonal_nombre"],
                            "jefe_zonal_telefono": r["jefe_zonal_telefono"],
                        },
                        ensure_ascii=False,
                    )
                    for r in new_rows
                ]
                phones_new = [r["telefono"] for r in new_rows]
                pdv_rows = await conn.fetch(
                    """
                    INSERT INTO dimer.puntos_venta
                        (razon_social, lista_precios_id, cuit, direccion, vendedor, vendedor_id, activo_ai, is_mock)
                    SELECT x.razon, 1, x.cuit, x.dir, x.vend, x.vid, true, false
                    FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::int[])
                         AS x(razon, cuit, dir, vend, vid)
                    RETURNING id
                    """,
                    razons,
                    cuits,
                    dirs,
                    labels,
                    vids,
                )
                pdv_ids = [int(r["id"]) for r in pdv_rows]
                client_rows = await conn.fetch(
                    """
                    INSERT INTO dimer.clients (
                        phone_number, nombre, razon_social, lista_precios_id, cuit, direccion,
                        vendedor, activo_ai, pdv_id, is_primary, is_mock, metadata
                    )
                    SELECT x.phone, x.razon, x.razon, 1, x.cuit, x.dir, x.vend, true, x.pdv, true, false, x.meta::jsonb
                    FROM unnest(
                        $1::varchar[], $2::text[], $3::text[], $4::text[], $5::text[], $6::int[], $7::text[]
                    ) AS x(phone, razon, cuit, dir, vend, pdv, meta)
                    RETURNING id
                    """,
                    phones_new,
                    razons,
                    cuits,
                    dirs,
                    labels,
                    pdv_ids,
                    metas,
                )
                new_ids = [int(r["id"]) for r in client_rows]
                created += len(new_ids)

            assign_cids = [r["_cid"] for r in reuse_rows] + new_ids
            assign_vids = [vend_ids[r["codigo_ruta"]] for r in reuse_rows] + [
                vend_ids[r["codigo_ruta"]] for r in new_rows
            ]
            assign_etq_ruta = [etq_by_ruta[r["codigo_ruta"]] for r in reuse_rows] + [
                etq_by_ruta[r["codigo_ruta"]] for r in new_rows
            ]
            if assign_cids:
                await conn.execute(
                    """
                    INSERT INTO dimer.vendedores_clientes (vendedor_id, cliente_id, activo)
                    SELECT x.vid, x.cid, true
                    FROM unnest($1::int[], $2::int[]) AS x(vid, cid)
                    ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true, updated_at = now()
                    """,
                    assign_vids,
                    assign_cids,
                )
                await conn.execute(
                    """
                    INSERT INTO dimer.clientes_etiquetas (client_id, etiqueta_id)
                    SELECT x.cid, $2
                    FROM unnest($1::int[]) AS x(cid)
                    ON CONFLICT (client_id, etiqueta_id) DO NOTHING
                    """,
                    assign_cids,
                    etq_litoral,
                )
                await conn.execute(
                    """
                    INSERT INTO dimer.clientes_etiquetas (client_id, etiqueta_id)
                    SELECT x.cid, x.etq
                    FROM unnest($1::int[], $2::int[]) AS x(cid, etq)
                    ON CONFLICT (client_id, etiqueta_id) DO NOTHING
                    """,
                    assign_cids,
                    assign_etq_ruta,
                )
            print(f"    lote ok · creados {created} · phone ya existía {skipped}", flush=True)

    counts = await conn.fetchrow(
        """
        SELECT json_build_object(
          'vendedores_litoral', (SELECT COUNT(*) FROM dimer.vendedores WHERE codigo_ruta IN ('9','28','29','30','31','NUEVO1','NUEVO2','JZ')),
          'clients', (SELECT COUNT(*) FROM dimer.clients),
          'etq_litoral', (SELECT COUNT(*) FROM dimer.clientes_etiquetas WHERE etiqueta_id = $1),
          'pdv', (SELECT COUNT(*) FROM dimer.puntos_venta)
        ) AS j
        """,
        etq_litoral,
    )
    return {
        "created": created,
        "updated": updated,
        "skipped_dup_phone": skipped,
        "vend_ids": vend_ids,
        "etq_litoral": etq_litoral,
        "counts": json.loads(counts["j"]) if isinstance(counts["j"], str) else counts["j"],
    }


async def create_template(conn: asyncpg.Connection) -> dict:
    key = (os.getenv("CREDENTIALS_MASTER_KEY") or "").strip()
    if not key:
        raise SystemExit("Falta CREDENTIALS_MASTER_KEY")
    fr = Fernet(key.encode("utf-8"))
    rows = await conn.fetch(
        """
        SELECT name, value_enc
        FROM public.tenant_secrets
        WHERE tenant_id = $1::uuid AND name = ANY($2::text[])
        """,
        TENANT_ID,
        ["whatsapp.long_live_token", "whatsapp.waba"],
    )
    secrets = {r["name"]: fr.decrypt(r["value_enc"].encode()).decode() for r in rows}
    token = secrets.get("whatsapp.long_live_token") or ""
    waba = secrets.get("whatsapp.waba") or ""
    if not token or not waba:
        raise SystemExit("Faltan secretos WhatsApp de dimer")

    payload = {
        "name": TEMPLATE_NAME,
        "language": "es",
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": TEMPLATE_BODY,
                "example": {"body_text": TEMPLATE_EXAMPLE},
            },
            {"type": "FOOTER", "text": "Dimer"},
        ],
    }
    print(f"[*] create template {TEMPLATE_NAME} en WABA dimer")
    status, body = graph_post_json(f"{GRAPH}/{waba}/message_templates", token, payload)
    print(f"    HTTP {status} · {json.dumps(body, ensure_ascii=False)[:500]}")
    if status not in (200, 201):
        return {"http": status, "meta": body, "db_id": None}

    row = await conn.fetchrow(
        """
        INSERT INTO public.meta_plantillas (tenant_id, template_name, category, variable_columns)
        VALUES ($1::uuid, $2, 'MARKETING', $3::jsonb)
        ON CONFLICT (tenant_id, template_name) DO UPDATE SET
            category = EXCLUDED.category,
            variable_columns = EXCLUDED.variable_columns,
            rejection_reason = NULL
        RETURNING id, template_name
        """,
        TENANT_ID,
        TEMPLATE_NAME,
        json.dumps(["vendedor"]),
    )
    print(f"    db {row['id']}")
    return {"http": status, "meta": body, "db_id": str(row["id"])}


async def main() -> int:
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        print("[FAIL] falta SUPABASE_DB_URL_POOLER")
        return 1
    print("Schema: dimer (repetido). Carga Litoral + plantilla WhatsApp.", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0, timeout=30, command_timeout=120)
    try:
        db_result = await load_db(conn)
        print("[*] DB", json.dumps(db_result["counts"], ensure_ascii=False), "created", db_result["created"], "updated", db_result["updated"])
        tpl = await create_template(conn)
        summary = {
            "schema": SCHEMA,
            "db": {k: db_result[k] for k in ("created", "updated", "skipped_dup_phone", "counts") if k in db_result},
            "template": tpl,
        }
        out = OUT / "litoral-carga-y-plantilla.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[*] resumen {out}")
        return 0 if tpl.get("http") in (200, 201) else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
