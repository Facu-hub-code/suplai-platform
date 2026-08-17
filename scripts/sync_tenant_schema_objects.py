"""
Script de sincronización y reparación de esquema DDL para tenants de Suplai Sales.
Copia/sincroniza:
  1. Tablas faltantes (con LIKE INCLUDING ALL).
  2. Funciones PL/pgSQL (set_updated_at, sync_conversation_on_message, on_pedido_confirmado_update_memory, etc.).
  3. Claves primarias e índices únicos/secundarios.
  4. Triggers en n8n_chat_histories, pedidos, productos, etc.

Uso:
  python scripts/sync_tenant_schema_objects.py --source gonzales --target valaice
"""

import argparse
import asyncio
import os
import re
import sys
import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def sync_schema(source: str, target: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL no encontrada en el entorno.")
        sys.exit(1)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        print(f"[*] Iniciando sincronización de esquema: {source} -> {target}")

        # 1. Verificar que el esquema target existe
        schema_exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1", target
        )
        if not schema_exists:
            print(f"[*] Creando esquema '{target}'...")
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{target}"')

        # 2. Copiar tablas faltantes usando LIKE INCLUDING ALL
        source_tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = $1 AND table_type = 'BASE TABLE'",
            source,
        )
        target_tables_rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = $1 AND table_type = 'BASE TABLE'",
            target,
        )
        target_tables = {r["table_name"] for r in target_tables_rows}

        for r in source_tables:
            tbl = r["table_name"]
            if tbl not in target_tables:
                print(f"  [+] Creando tabla faltante '{target}.{tbl}'...")
                await conn.execute(
                    f'CREATE TABLE "{target}"."{tbl}" (LIKE "{source}"."{tbl}" INCLUDING ALL)'
                )

        # 3. Sincronizar Funciones PL/pgSQL
        print(f"[*] Sincronizando funciones PL/pgSQL de '{source}' a '{target}'...")
        functions = await conn.fetch(
            """
            SELECT p.proname, pg_get_functiondef(p.oid) as def
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = $1
            """,
            source,
        )
        for fn in functions:
            fn_name = fn["proname"]
            fn_def = fn["def"]
            # Reemplazar nombre del esquema fuente por target
            fn_def_target = re.sub(
                r"\b" + re.escape(source) + r"\b", target, fn_def
            )
            print(f"  [+] Aplicando función '{target}.{fn_name}()'...")
            await conn.execute(fn_def_target)

        # 4. Sincronizar Índices y Claves Primarias
        print(f"[*] Sincronizando índices y PKs de '{source}' a '{target}'...")
        source_indexes = await conn.fetch(
            "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = $1",
            source,
        )
        target_indexes_rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname = $1", target
        )
        target_indexes = {r["indexname"] for r in target_indexes_rows}

        for idx in source_indexes:
            idx_name = idx["indexname"]
            tbl_name = idx["tablename"]
            idx_def = idx["indexdef"]

            # Generar nombre esperado en target
            target_idx_name = idx_name.replace(source, target)
            if target_idx_name in target_indexes or idx_name in target_indexes:
                continue

            # Adaptar DDL del índice
            idx_def_target = re.sub(
                r"\b" + re.escape(source) + r"\b", target, idx_def
            )
            if idx_name != target_idx_name:
                idx_def_target = idx_def_target.replace(idx_name, target_idx_name)

            print(f"  [+] Creando índice '{target_idx_name}' en '{target}.{tbl_name}'...")
            try:
                await conn.execute(idx_def_target)
            except Exception as e:
                print(f"  [!] Advertencia al crear índice '{target_idx_name}': {e}")

        # 5. Sincronizar Triggers
        print(f"[*] Sincronizando triggers de '{source}' a '{target}'...")
        triggers = await conn.fetch(
            """
            SELECT t.tgname, c.relname as tablename, pg_get_triggerdef(t.oid) as def
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = $1 AND NOT t.tgisinternal
            """,
            source,
        )

        for trg in triggers:
            trg_name = trg["tgname"]
            tbl_name = trg["tablename"]
            trg_def = trg["def"]

            # Adaptar DDL del trigger
            trg_def_target = re.sub(
                r"\b" + re.escape(source) + r"\b", target, trg_def
            )
            # Asegurar que llamadas a funciones un-namespaced como set_updated_at() llamen al esquema target
            trg_def_target = re.sub(
                r"EXECUTE FUNCTION (?!'|\"|" + re.escape(target) + r"\.)([a-zA-Z0-9_]+)\(\)",
                r"EXECUTE FUNCTION " + target + r".\1()",
                trg_def_target,
            )

            print(f"  [+] Aplicando trigger '{trg_name}' en '{target}.{tbl_name}'...")
            await conn.execute(
                f'DROP TRIGGER IF EXISTS "{trg_name}" ON "{target}"."{tbl_name}"'
            )
            await conn.execute(trg_def_target)

        print(
            f"[SUCCESS] Esquema '{target}' sincronizado al 100% con '{source}'."
        )

    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza/Repara DDL de un esquema tenant Suplai desde un esquema de referencia."
    )
    parser.add_argument(
        "--source",
        default="gonzales",
        help="Esquema fuente de referencia (default: gonzales)",
    )
    parser.add_argument(
        "--target", required=True, help="Esquema destino a sincronizar (ej: valaice)"
    )
    args = parser.parse_args()
    asyncio.run(sync_schema(args.source, args.target))


if __name__ == "__main__":
    main()
