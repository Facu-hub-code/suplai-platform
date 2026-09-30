#!/usr/bin/env python3
"""Reasigna el catálogo de dimer a una taxonomía de 4 niveles por tipo de producto.

Tenant: dimer. No toca otros schemas. Sin secretos.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SCHEMA = "dimer"
BATCH = 80


def _fold(value: str) -> str:
    n = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _brand(nombre: str) -> str:
    n = _fold(nombre)
    brands = [
        ("mccain", "McCain"),
        ("minuto verde", "Minuto Verde"),
        ("minutito", "Minuto Verde"),
        ("savory", "Savory"),
        ("chamonix", "Savory"),
        ("sadia", "Sadia"),
        ("iansa", "Iansa"),
        ("interagro", "Interagro"),
        ("huilco", "Huilco"),
        ("la hacienda", "La Hacienda"),
        ("qualy", "Qualy"),
        ("bonella", "Bonella"),
        ("gordon fish", "Gordon Fish"),
        ("ft foods", "FT Foods"),
        ("fundo sur", "Fundo Sur"),
        ("country fries", "Country Fries"),
        ("one fry", "One Fry"),
        ("caterpak", "Caterpak"),
        ("mimet", "Mimet"),
        ("framec", "Framec"),
        ("fenice", "Fenice"),
        ("iarp", "Iarp"),
        ("nestle", "Nestlé"),
    ]
    for needle, label in brands:
        if needle in n:
            return label
    return "Sin marca"


def classify(nombre: str, code: str) -> dict[str, str]:
    n = _fold(nombre)
    c = _fold(code)
    brand = _brand(nombre)

    if any(
        k in n
        for k in (
            "congeladora",
            "freezer",
            "frezzer",
            "barquillera",
            "conservadora",
            "cooler",
            "granizad",
            "horno",
            "honro",
            "kiosko",
            "carro push",
            "cold car",
            "scoop",
            "isetta",
            "island",
            "mimet",
            "framec",
            "fenice",
            "ventus",
            "millenium",
            "close cabin",
            "upright",
        )
    ) or c in {"j13", "mimet", "skyspot", "smart ip", "vsj635", "barq", "ig321"}:
        if "barquillera" in n or c == "barq":
            return {"1": "Equipamiento", "2": "Exhibición", "3": "Barquilleras", "4": brand}
        if "carro" in n or "cold car" in n:
            return {"1": "Equipamiento", "2": "Movilidad", "3": "Carros", "4": brand}
        if "graniz" in n:
            return {"1": "Equipamiento", "2": "Máquinas", "3": "Granizadoras", "4": brand}
        if "horno" in n or "honro" in n:
            return {"1": "Equipamiento", "2": "Máquinas", "3": "Hornos", "4": brand}
        if "kiosko" in n:
            return {"1": "Equipamiento", "2": "Exhibición", "3": "Kioskos", "4": brand}
        if any(k in n for k in ("vertical", "upright", "vv-")):
            return {"1": "Equipamiento", "2": "Congeladoras", "3": "Verticales", "4": brand}
        if "scoop" in n:
            return {"1": "Equipamiento", "2": "Congeladoras", "3": "Scooping", "4": brand}
        return {"1": "Equipamiento", "2": "Congeladoras", "3": "Horizontales", "4": brand}

    if any(k in n for k in ("manga vaso", "manga tapa", "paletilla madera")):
        return {"1": "Abarrotes", "2": "Descartables", "3": "Vasos y tapas", "4": brand}

    ice_needles = (
        "helado",
        "bote ",
        "litro ",
        "mega ",
        "danky",
        "chomp",
        "crazy",
        "chocolito",
        "trululu",
        "kiko",
        "kriko",
        "lolly",
        "sahne nuss",
        "hel paleta",
        "mini paleta",
        "hel mp",
        "cassata",
        "almendrado",
        "savory",
        "chamonix",
        "centella",
        "charlot",
        "cremeria",
        "pura fruta",
        "xplori",
        "triton",
        "trencito",
        "sangurucho",
        "egocentrico",
        "crocanty",
        "kit kat",
        "delta mega",
        "cola de tigre",
        "galactea",
        "fini ",
    )
    if any(k in n for k in ice_needles) and "congeladora" not in n and "vacuno" not in n and "vacio" not in n:
        agua = any(
            k in n
            for k in (
                "de agua",
                "lolly",
                "centella",
                "kiko",
                "chocolito",
                "trululu",
                "colores",
                "sandia",
                "pura fruta",
                "crocanty",
                "egocentrico",
                "triton",
                "trencito",
                "xplori",
                "fini",
                "chomp",
            )
        )
        if agua:
            return {"1": "Helados y Postres", "2": "Paletas", "3": "Helados de agua", "4": brand}
        if any(k in n for k in ("bote", "litro", "charlot", "cassata", "cremeria", "chamonix")):
            return {"1": "Helados y Postres", "2": "Potes y litros", "3": "Helados de crema", "4": brand}
        return {"1": "Helados y Postres", "2": "Paletas", "3": "Helados de crema", "4": brand}

    if any(k in n for k in ("papa", "papas", "smiles", "country fries", "one fry", "caterpak")):
        if "duquesa" in n:
            return {"1": "Papas y Aperitivos", "2": "Papas prefritas", "3": "Duquesa", "4": brand}
        if "gajo" in n:
            return {"1": "Papas y Aperitivos", "2": "Papas prefritas", "3": "Gajos", "4": brand}
        if "smiles" in n:
            return {"1": "Papas y Aperitivos", "2": "Papas prefritas", "3": "Formas", "4": brand}
        return {"1": "Papas y Aperitivos", "2": "Papas prefritas", "3": "Corte regular", "4": brand}

    if "pulpa" in n and "deshuesada" in n:
        return {"1": "Carnes", "2": "Vacuno", "3": "Cortes al vacío", "4": brand}
    if "pulpa" in n:
        return {"1": "Frutas Congeladas", "2": "Pulpas", "3": "Pulpas de fruta", "4": brand}

    if any(
        k in n
        for k in (
            "arandano",
            "frambuesa",
            "frutilla",
            "mango",
            "mora",
            "pina cubo",
            "piña cubo",
            "pina en trozo",
            "piña en trozo",
            "mix frutos",
            "granado",
            "p. granado",
        )
    ):
        return {"1": "Frutas Congeladas", "2": "Frutas IQF", "3": "Berries y tropicales", "4": brand}

    if any(
        k in n
        for k in (
            "arveja",
            "choclo",
            "brocoli",
            "cebolla",
            "champi",
            "coliflor",
            "esparrago",
            "espinaca",
            "habas",
            "jardinera",
            "pimenton",
            "zapallo",
            "aros de cebolla",
            "primavera",
            "poroto verde",
            "p.verde",
        )
    ):
        return {"1": "Vegetales Congelados", "2": "Hortalizas", "3": "Mix y cortes", "4": brand}

    if any(k in n for k in ("merluza", "salmon", "camaron", "reineta", "pececitos", "surtido de marisco")):
        if "camaron" in n:
            return {"1": "Pescados y Mariscos", "2": "Mariscos", "3": "Camarón", "4": brand}
        if "hamburguesa" in n or "nugget" in n or "croqueta" in n or "pececitos" in n:
            return {"1": "Pescados y Mariscos", "2": "Rebozados", "3": "Hamburguesas y nuggets", "4": brand}
        return {"1": "Pescados y Mariscos", "2": "Filetes", "3": "Pescado blanco", "4": brand}

    if any(
        k in n
        for k in (
            "pollo",
            "alitas",
            "pechuga",
            "trutro",
            "filetito",
            "nugget",
            "milanesa",
            "golden chicken",
            "supremitas",
            "pavita",
        )
    ) and "hamburguesa" not in n:
        if "nugget" in n or "reboz" in n or "reb " in n or "reb." in n or "golden" in n or "supremitas" in n or "milanesa" in n:
            return {"1": "Aves", "2": "Rebozados", "3": "Nuggets y milanesas", "4": brand}
        if "alitas" in n:
            return {"1": "Aves", "2": "Pollo", "3": "Alitas", "4": brand}
        return {"1": "Aves", "2": "Pollo", "3": "Cortes de pollo", "4": brand}

    if "hamburguesa" in n:
        if "garbanzo" in n or "lenteja" in n:
            return {"1": "Comidas Preparadas", "2": "Hamburguesas", "3": "Vegetales", "4": brand}
        return {"1": "Carnes", "2": "Hamburguesas", "3": "Vacuno", "4": brand}

    if any(
        k in n
        for k in (
            "vacuno",
            "asado",
            "asiento",
            "lomo",
            "ganso",
            "posta",
            "huachalomo",
            "tapapecho",
            "sobrecostilla",
            "abastero",
            "churrasco",
            "molida",
            "cubitos",
            "tiritas",
            "carne magra",
            "carne mechada",
            "choclillo",
            "filete vacuno",
            "plateada",
            "punta",
            "cogote",
        )
    ) and "cerdo" not in n:
        if "molida" in n or "carne magra" in n:
            return {"1": "Carnes", "2": "Vacuno", "3": "Molida", "4": brand}
        return {"1": "Carnes", "2": "Vacuno", "3": "Cortes al vacío", "4": brand}

    if any(k in n for k in ("cerdo", "costillar", "chuleta", "jamon", "baby back", "ribs")):
        return {"1": "Carnes", "2": "Cerdo", "3": "Cortes de cerdo", "4": brand}

    if any(
        k in n
        for k in (
            "lasagna",
            "pizza",
            "hot bowls",
            "humitas",
            "chapsui",
            "arrollado",
            "pasta de choclo",
            "sofrito",
            "wok",
            "albondiga",
            "donut",
            "muffin",
            "megabites",
        )
    ):
        if "pizza" in n:
            return {"1": "Comidas Preparadas", "2": "Pizzas", "3": "Pizzas congeladas", "4": brand}
        if "lasagna" in n:
            return {"1": "Comidas Preparadas", "2": "Pastas", "3": "Lasañas", "4": brand}
        if "donut" in n or "muffin" in n or "megabites" in n:
            return {"1": "Comidas Preparadas", "2": "Pastelería", "3": "Donas y muffins", "4": brand}
        return {"1": "Comidas Preparadas", "2": "Listos para calentar", "3": "Platos preparados", "4": brand}

    if any(k in n for k in ("queso", "mantequilla", "margarina", "bonella", "dorina", "sucedaneo")):
        if "queso" in n or "sucedaneo" in n:
            return {"1": "Lácteos", "2": "Quesos", "3": "Quesos laminados y barras", "4": brand}
        return {"1": "Lácteos", "2": "Mantecas", "3": "Mantequilla y margarina", "4": brand}

    if any(k in n for k in ("bilz", "jugo de limon")):
        return {"1": "Bebidas", "2": "Gaseosas y jugos", "3": "Listos para beber", "4": brand}

    if any(
        k in n
        for k in (
            "azucar",
            "arroz",
            "garbanzo",
            "lenteja",
            "poroto",
            "aceite",
            "endulzante",
            "sucralosa",
            "cero k",
            "chancaca",
            "galleta",
            "nescafe",
            "cafe ",
            "te chai",
            "milo",
            "ensalada lista",
            "ens.lista",
        )
    ):
        if "galleta" in n:
            return {"1": "Abarrotes", "2": "Galletas", "3": "Galletas empaquetadas", "4": brand}
        if "azucar" in n or "endulzante" in n or "sucralosa" in n or "cero k" in n or "chancaca" in n:
            return {"1": "Abarrotes", "2": "Endulzantes", "3": "Azúcar y sucralosa", "4": brand}
        if "aceite" in n:
            return {"1": "Abarrotes", "2": "Aceites", "3": "Aceites de cocina", "4": brand}
        if any(k in n for k in ("nescafe", "cafe", "te chai", "milo")):
            return {"1": "Abarrotes", "2": "Infusiones", "3": "Café y té", "4": brand}
        return {"1": "Abarrotes", "2": "Despensa", "3": "Granos y conservas", "4": brand}

    if "manteca de cerdo" in n:
        return {"1": "Carnes", "2": "Cerdo", "3": "Subproductos", "4": brand}

    if "cacao" in n:
        return {"1": "Abarrotes", "2": "Repostería", "3": "Cacao y chocolate", "4": brand}

    return {"1": "Abarrotes", "2": "Otros", "3": "Sin clasificar fino", "4": brand}


def _prepare_env() -> None:
    env_path = BACKEND / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")


def _db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or ""
    return url.replace(":5432/", ":6543/")


async def load_products(conn) -> list[dict]:
    rows = await conn.fetch(
        f'SELECT product_code, nombre FROM "{SCHEMA}".productos ORDER BY nombre'
    )
    return [{"product_code": r["product_code"], "nombre": r["nombre"]} for r in rows]


def build_proposal(products: list[dict]) -> dict:
    items = []
    for p in products:
        items.append(
            {
                "product_code": p["product_code"],
                "nombre": p["nombre"],
                "tags": classify(p["nombre"], p["product_code"]),
            }
        )
    return {
        "schema": SCHEMA,
        "source": "reasignar_categorias.py reglas por tipo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products": items,
    }


async def apply_proposal(conn, proposal: dict) -> dict:
    products = proposal["products"]
    category_cache: dict[tuple[str, int | None], int] = {}
    assignments: list[tuple[str, int]] = []
    used_ids: set[int] = set()

    async with conn.transaction():
        await conn.execute(f'DELETE FROM "{SCHEMA}".product_categories')
        for item in products:
            parent_id: int | None = None
            for level in ("1", "2", "3", "4"):
                name = " ".join(str(item["tags"][level]).split())
                key = (name.casefold(), parent_id)
                category_id = category_cache.get(key)
                if category_id is None:
                    category_id = await conn.fetchval(
                        f"""
                        SELECT id FROM "{SCHEMA}".categorias
                        WHERE lower(name) = $1 AND parent_id IS NOT DISTINCT FROM $2
                        """,
                        name.casefold(),
                        parent_id,
                    )
                    if category_id is None:
                        category_id = await conn.fetchval(
                            f"""
                            INSERT INTO "{SCHEMA}".categorias
                              (name, description, parent_id, sort_order, created_at, updated_at)
                            VALUES ($1, $2, $3, 0, now(), now())
                            RETURNING id
                            """,
                            name,
                            f"Nivel {level} taxonomía comercial Dimer",
                            parent_id,
                        )
                    category_cache[key] = int(category_id)
                used_ids.add(int(category_id))
                assignments.append((item["product_code"], int(category_id)))
                parent_id = int(category_id)

        for i in range(0, len(assignments), BATCH):
            await conn.executemany(
                f"""
                INSERT INTO "{SCHEMA}".product_categories (product_code, categoria_id)
                VALUES ($1, $2)
                ON CONFLICT (product_code, categoria_id) DO NOTHING
                """,
                assignments[i : i + BATCH],
            )

        deleted = 0
        used = list(used_ids)
        while True:
            result = await conn.execute(
                f"""
                DELETE FROM "{SCHEMA}".categorias c
                WHERE c.id <> ALL($1::int[])
                  AND NOT EXISTS (
                    SELECT 1 FROM "{SCHEMA}".categorias ch WHERE ch.parent_id = c.id
                  )
                """,
                used,
            )
            n = int(result.split()[-1]) if result else 0
            deleted += n
            if n == 0:
                break

    return {
        "categorias": int(await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".categorias')),
        "asignaciones": int(await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".product_categories')),
        "productos_con_cat": int(
            await conn.fetchval(f'SELECT count(DISTINCT product_code) FROM "{SCHEMA}".product_categories')
        ),
        "huerfanas_borradas": deleted,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    _prepare_env()
    import asyncpg

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        products = await load_products(conn)
        proposal = build_proposal(products)
        OUT.mkdir(parents=True, exist_ok=True)
        out_path = OUT / "phase-01-1-propuesta-categorias.json"
        out_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        counts = Counter(p["tags"]["1"] for p in proposal["products"])
        print(json.dumps({"schema": SCHEMA, "productos": len(products), "por_l1": dict(counts)}, ensure_ascii=False, indent=2))
        print(f"propuesta: {out_path}")
        if not args.apply:
            print("dry-run: pasá --apply para escribir en dimer")
            return 0
        stats = await apply_proposal(conn, proposal)
        print(json.dumps({"apply": stats}, ensure_ascii=False, indent=2))
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
