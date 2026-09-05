#!/usr/bin/env python3
"""Crea dimer_litoral_contacto_v2 y deja {{1}} nombre, {{2}} vendedor, {{3}} teléfono.

Schema: dimer. Pooler 6543, statement_cache_size=0. No envía mensajes.
"""
from __future__ import annotations

import csv
import json
import os
import re
import ssl
import urllib.error
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
TEMPLATE_NAME = "dimer_litoral_contacto_v2"
GRAPH = "https://graph.facebook.com/v21.0"
CTX = ssl.create_default_context(cafile=certifi.where())
BATCH = 80

load_dotenv(BACKEND_ENV)

# Sin espacios dobles. {{2}} se repite (nombre del vendedor). No empieza ni termina en variable.
TEMPLATE_BODY = (
    "Hola, {{1}}! Te escribo de parte del equipo de Dimer\n"
    "\n"
    "Queríamos dejarte a mano el contacto directo de {{2}}, que es tu vendedor asignado "
    "para ver cualquier pedido o duda de tu zona: {{3}}\n"
    "De todas formas, si en algún momento no logras dar con {{2}}, puedes escribirle "
    "directamente a Francisco Díaz, nuestro jefe de ventas, al +56 9 6191 6961.\n"
    "Cualquier cosa que necesites me avisas por acá! Que tengas un excelente día."
)
TEMPLATE_EXAMPLE = [["Cristian", "Doralisa Vivencio", "+56 9 7988 8434"]]
VARIABLE_COLUMNS = ["nombre", "vendedor", "email"]

LEGAL = re.compile(
    r"\b(SPA|LTDA|E\.?I\.?R\.?L\.?|LIMITADA|S\.?A\.?|COMERCIAL|ALMAC[EÉ]N|"
    r"MINIMARKET|SUPERMERCADO|BOTILLER[IÍ]A|RESTAURANT|PANADER[IÍ]A|"
    r"DISTRIBUIDORA|SOC\.|CIA\.|CÍA\.|EMPRESA)\b",
    re.I,
)
PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "DA", "DO", "SAN", "SANTA"}
GIVEN = {
    "AARON", "ABRAHAM", "ADELA", "ADRIAN", "ADRIANA", "AGUSTIN", "AGUSTINA", "AIDA",
    "ALBA", "ALBERTO", "ALDO", "ALEJANDRA", "ALEJANDRO", "ALEX", "ALEXANDRA", "ALEXIS",
    "ALFONSO", "ALFREDO", "ALICIA", "ALMA", "ALONSO", "ALVARO", "AMALIA", "AMANDA",
    "AMELIA", "ANA", "ANABEL", "ANDREA", "ANDRES", "ANGEL", "ANGELICA", "ANGELINA",
    "ANITA", "ANTONIA", "ANTONIO", "ARACELY", "ARIEL", "ARMANDO", "ARTURO", "AURORA",
    "AYLIN", "AZUCENA", "BARBARA", "BEATRIZ", "BELEN", "BERNARDA", "BERNARDO", "BETTY",
    "BLANCA", "BRENDA", "BRUNO", "CAMILA", "CAMILO", "CARLA", "CARLOS", "CARMINA",
    "CARMEN", "CAROLA", "CAROLINA", "CATALINA", "CECILIA", "CELIA", "CESAR", "CHRISTIAN",
    "CINDY", "CINTIA", "CLARA", "CLAUDIA", "CLAUDIO", "CONCEPCION", "CONSTANZA",
    "CONSUELO", "CRISTIAN", "CRISTINA", "CRISTOBAL", "DANIEL", "DANIELA", "DAVID",
    "DEBORAH", "DELIA", "DENISE", "DENISSE", "DIANA", "DIEGO", "DINA", "DOLLY",
    "DOLORES", "DORA", "DORIS", "EDGAR", "EDITH", "EDITHA", "EDUARDO", "ELBA", "ELENA",
    "ELIANA", "ELISA", "ELIZABETH", "ELOISA", "ELSA", "ELVIRA", "EMILIA", "EMILIO",
    "EMMA", "ENRIQUE", "ERIC", "ERICA", "ERICK", "ERIKA", "ERNESTO", "ESPERANZA",
    "ESTEBAN", "ESTELA", "ESTHER", "EUGENIA", "EVA", "EVELYN", "FABIAN", "FABIOLA",
    "FANNY", "FATIMA", "FELIPE", "FERNANDO", "FRANCISCA", "FRANCISCO", "FRESIA",
    "GABRIEL", "GABRIELA", "GENESIS", "GEORGINA", "GERARDO", "GERMAN", "GINA",
    "GLADYS", "GLORIA", "GONZALO", "GRACIELA", "GUILLERMO", "GUSTAVO", "HAYDEE",
    "HECTOR", "HELEN", "HELENA", "HENRY", "HERNAN", "HILDA", "HORACIO", "HUGO",
    "HUMBERTO", "IGNACIO", "ILIANA", "INES", "INGRID", "IRENE", "IRMA", "ISABEL",
    "ISIDORA", "IVAN", "IVETTE", "IVONNE", "JACQUELINE", "JAIME", "JANET", "JAQUELINE",
    "JAVIER", "JAVIERA", "JEANETTE", "JEANNETTE", "JENNIFER", "JESSICA", "JIMENA",
    "JOAQUIN", "JORGE", "JOSE", "JOSEFA", "JUAN", "JUANA", "JULIAN", "JULIANA",
    "JULIETA", "JULIO", "KARINA", "KARLA", "KATHERINE", "KATHERINA", "LARA", "LAURA",
    "LEANDRO", "LEONARDO", "LEONEL", "LEONOR", "LIDIA", "LILIAN", "LILIANA", "LIZ",
    "LORENA", "LORETO", "LUCAS", "LUCIA", "LUCY", "LUIS", "LUZ", "MACARENA", "MAGDALENA",
    "MANUEL", "MARCELA", "MARCO", "MARCOS", "MARGARITA", "MARIA", "MARIBEL", "MARIELA",
    "MARINA", "MARIO", "MARISOL", "MARITZA", "MARTA", "MARTHA", "MARTINA", "MATIAS",
    "MAURICIO", "MAXIMILIANO", "MELANIE", "MELISSA", "MERCEDES", "MICHAEL", "MICHELLE",
    "MIGUEL", "MILTON", "MIRIAM", "MONICA", "MYRIAM", "NANCY", "NATALIA", "NATALY",
    "NELSON", "NELLY", "NICOLAS", "NICOLE", "NIDIA", "NOEMI", "NORMA", "OCTAVIO",
    "OFELIA", "OLGA", "OLIVIA", "ORLANDO", "OSCAR", "OSVALDO", "PABLO", "PALOMA",
    "PAMELA", "PAOLA", "PASCUAL", "PATRICIA", "PATRICIO", "PAULA", "PAULINA", "PEDRO",
    "PILAR", "PRISCILA", "PRISCILLA", "RAFAEL", "RAMIRO", "RAMON", "RAQUEL", "RAUL",
    "REBECA", "RENE", "RICARDO", "RITA", "ROBERTO", "ROCIO", "RODRIGO", "ROLANDO",
    "ROMINA", "ROSA", "ROSARIO", "RUBEN", "RUTH", "SALVADOR", "SAMUEL", "SANDRA",
    "SANTIAGO", "SEBASTIAN", "SERGIO", "SILVIA", "SOFIA", "SOLANGE", "SOLEDAD",
    "SONIA", "SUSANA", "TAMARA", "TATIANA", "TERESA", "TOMAS", "TRINIDAD", "ULISES",
    "VALENTINA", "VALERIA", "VANESSA", "VERONICA", "VICENTE", "VICTOR", "VICTORIA",
    "VINCENTE", "VIOLETA", "VIVIAN", "VIVIANA", "WALTER", "WILSON", "XIMENA",
    "XIOMARA", "YANINA", "YANARA", "YASNA", "YESENIA", "YOLANDA",
}


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def fmt_cl_mobile(digits: str) -> str:
    d = "".join(c for c in digits if c.isdigit())
    if d.startswith("56") and len(d) >= 11:
        rest = d[2:]
        if rest.startswith("9") and len(rest) >= 9:
            return f"+56 9 {rest[1:5]} {rest[5:9]}"
    return f"+{d}" if d else ""


def title_es(word: str) -> str:
    return word[:1].upper() + word[1:].lower() if word else word


def is_company(razon: str) -> bool:
    return bool(LEGAL.search(razon or ""))


def nombre_de_pila(razon: str) -> str:
    if is_company(razon):
        return "Cliente"
    tokens = [t for t in (razon or "").replace(",", " ").split() if t]
    if not tokens:
        return "Cliente"
    if tokens[0].upper() in GIVEN:
        return title_es(tokens[0])
    if len(tokens) >= 3:
        rest = tokens[2:]
        while rest and rest[0].upper() in PARTICLES:
            rest = rest[1:]
        if rest:
            return title_es(rest[0])
    return title_es(tokens[0])


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
    with (OUT / "litoral-destinatarios-whatsapp.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


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
        ],
    }
    print(f"[*] create template {TEMPLATE_NAME} en WABA dimer", flush=True)
    status, body = graph_post_json(f"{GRAPH}/{waba}/message_templates", token, payload)
    print(f"    HTTP {status} · {json.dumps(body, ensure_ascii=False)[:500]}", flush=True)
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
        json.dumps(VARIABLE_COLUMNS),
    )
    print(f"    db {row['id']}", flush=True)
    return {"http": status, "meta": body, "db_id": str(row["id"])}


async def update_clientes(conn: asyncpg.Connection) -> dict:
    dest = load_destinatarios()
    phone_to_row = {}
    for r in dest:
        digits = "".join(c for c in (r.get("telefono") or "") if c.isdigit())
        if digits:
            phone_to_row[digits] = r

    clients = await conn.fetch(
        """
        SELECT id, phone_number, nombre, nombre_de_pila, email, vendedor
        FROM dimer.clients
        WHERE metadata->>'origen' = 'litoral_7_vendedores'
        """
    )
    updates = []
    missing = 0
    kept_pila = 0
    for cli in clients:
        digits = "".join(c for c in str(cli["phone_number"] or "") if c.isdigit())
        src = phone_to_row.get(digits)
        if not src:
            missing += 1
            continue
        vend_name = (src.get("vendedor_nombre") or "").strip()
        vend_phone = fmt_cl_mobile(src.get("vendedor_telefono") or "")
        existing_pila = (cli["nombre_de_pila"] or "").strip()
        if existing_pila:
            pila = existing_pila
            kept_pila += 1
        else:
            pila = nombre_de_pila(cli["nombre"] or src.get("razon_social") or "")
        email_val = (cli["email"] or "").strip() or vend_phone
        updates.append((int(cli["id"]), vend_name, email_val, pila, vend_phone))

    csv_path = OUT / "litoral-nombres-pila-v2.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["client_id", "nombre", "nombre_de_pila", "vendedor", "telefono_vendedor"])
        w.writeheader()
        by_id = {int(c["id"]): c for c in clients}
        for cid, vend_name, email_val, pila, vend_phone in updates:
            w.writerow(
                {
                    "client_id": cid,
                    "nombre": by_id[cid]["nombre"],
                    "nombre_de_pila": pila,
                    "vendedor": vend_name,
                    "telefono_vendedor": vend_phone,
                }
            )

    updated = 0
    async with conn.transaction():
        for batch in chunks(updates, BATCH):
            ids = [x[0] for x in batch]
            vends = [x[1] for x in batch]
            emails = [x[2] for x in batch]
            pilas = [x[3] for x in batch]
            phones = [x[4] for x in batch]
            await conn.execute(
                """
                UPDATE dimer.clients AS c
                SET vendedor = u.vendedor,
                    email = CASE
                        WHEN NULLIF(btrim(c.email), '') IS NULL THEN u.email
                        ELSE c.email
                    END,
                    nombre_de_pila = CASE
                        WHEN NULLIF(btrim(c.nombre_de_pila), '') IS NULL THEN u.pila
                        ELSE c.nombre_de_pila
                    END,
                    metadata = COALESCE(c.metadata, '{}'::jsonb) || jsonb_build_object(
                        'litoral_plantilla', 'dimer_litoral_contacto_v2',
                        'vendedor_telefono_fmt', u.phone
                    ),
                    updated_at = now()
                FROM unnest($1::int[], $2::text[], $3::text[], $4::text[], $5::text[])
                    AS u(id, vendedor, email, pila, phone)
                WHERE c.id = u.id
                """,
                ids,
                vends,
                emails,
                pilas,
                phones,
            )
            updated += len(batch)
            print(f"    update lote {updated}/{len(updates)}", flush=True)

    counts = await conn.fetchrow(
        """
        SELECT json_build_object(
            'litoral', COUNT(*),
            'con_pila', COUNT(*) FILTER (WHERE NULLIF(btrim(nombre_de_pila), '') IS NOT NULL),
            'vendedor_sin_al', COUNT(*) FILTER (
                WHERE vendedor IS NOT NULL AND vendedor NOT ILIKE '% al +%'
            ),
            'email_tel', COUNT(*) FILTER (WHERE email LIKE '+56%'),
            'muestra', (
                SELECT json_agg(s)
                FROM (
                    SELECT id, nombre, nombre_de_pila, vendedor, email
                    FROM dimer.clients
                    WHERE metadata->>'origen' = 'litoral_7_vendedores'
                    ORDER BY id
                    LIMIT 5
                ) s
            )
        ) AS j
        FROM dimer.clients
        WHERE metadata->>'origen' = 'litoral_7_vendedores'
        """
    )
    return {
        "matched": len(updates),
        "missing_phone_map": missing,
        "kept_pila": kept_pila,
        "updated": updated,
        "csv": str(csv_path),
        "counts": json.loads(counts["j"]) if isinstance(counts["j"], str) else counts["j"],
    }


async def main() -> int:
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        print("[FAIL] falta SUPABASE_DB_URL_POOLER")
        return 1
    if re.search(r"[ ]{2,}", TEMPLATE_BODY):
        print("[FAIL] el body tiene espacios dobles")
        return 1
    print("Schema: dimer (repetido). Plantilla Litoral v2 + datos de variables.", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0, timeout=30, command_timeout=120)
    try:
        tpl = await create_template(conn)
        db_result = await update_clientes(conn)
        summary = {"schema": SCHEMA, "template": tpl, "clientes": db_result}
        out = OUT / "litoral-plantilla-v2.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[*] resumen {out}", flush=True)
        return 0 if tpl.get("http") in (200, 201) else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
