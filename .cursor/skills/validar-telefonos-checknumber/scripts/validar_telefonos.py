#!/usr/bin/env python3
"""Valida en bulk los teléfonos de {schema}.clients con checknumber.ai.

Fases: extraer → enviar → bajar → aplicar.
No llama a la API ni escribe la base sin --confirmar.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

YES_TTL = timedelta(days=90)
NO_TTL = timedelta(days=30)
API_BASE = "https://api.checknumber.ai"
PROVIDER_ID = "checknumber"
TASK_TYPE = "ws_active"
POLL_DEADLINE_S = 15 * 60


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = repo_root()
    for path in (
        root / ".env",
        root / "backend" / ".env",
        root.parent / "backend-supabase" / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)


def require_schema(schema: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema or ""):
        raise SystemExit(f"schema inválido: {schema!r}")
    return schema


def to_e164_digits(raw: str) -> str | None:
    """Normaliza un teléfono cargado en Argentina a dígitos E.164.

    - 54 + 12 o 13 dígitos se deja.
    - 11 dígitos que empiezan en 1 se deja (NANP, p. ej. Benfresh).
    - 10 u 11 dígitos nacionales se prefijan con 54.
    - Otro internacional de 11 a 15 dígitos se deja.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        return None
    if digits.startswith("54"):
        return digits if len(digits) in (12, 13) else None
    if digits.startswith("1") and len(digits) == 11:
        return digits
    if len(digits) in (10, 11):
        return "54" + digits
    if 11 <= len(digits) <= 15:
        return digits
    return None


def parse_yes_no(value: object) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"yes", "y", "true", "1", "si", "sí"}:
        return True
    if text in {"no", "n", "false", "0"}:
        return False
    return None


def parse_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text or not re.fullmatch(r"-?\d+", text):
        return None
    return int(text)


def row_get(row: dict, *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for name in names:
        value = lowered.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def lote_dir(schema: str, stamp: str | None = None) -> Path:
    base = repo_root() / "implementacion" / schema / "outputs" / "checknumber"
    if stamp:
        return base / stamp
    if not base.exists():
        raise SystemExit(f"No hay lotes en {base}")
    dirs = sorted(p for p in base.iterdir() if p.is_dir())
    if not dirs:
        raise SystemExit(f"No hay lotes en {base}")
    return dirs[-1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dsn_ok(dsn: str) -> str:
    parsed = urllib.parse.urlparse(dsn)
    if parsed.port != 6543:
        raise SystemExit(
            f"SUPABASE_DB_URL tiene que usar el pooler en el puerto 6543 (ahora: {parsed.port})."
        )
    return dsn


def connect():
    import asyncpg

    load_env()
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Falta SUPABASE_DB_URL (pooler, puerto 6543).")
    return asyncpg.connect(dsn_ok(dsn), statement_cache_size=0)


def api_key() -> str:
    load_env()
    key = os.environ.get("CHECKNUMBER_API_KEY", "").strip()
    if not key:
        raise SystemExit("Falta CHECKNUMBER_API_KEY.")
    return key


def api_request(method: str, path: str, *, fields: dict | None = None, file_bytes: bytes | None = None, timeout: int = 60) -> tuple[int, dict | str]:
    url = API_BASE + path
    headers = {"X-API-Key": api_key()}
    data = None
    if file_bytes is not None or fields:
        boundary = "----suplai" + uuid.uuid4().hex
        chunks: list[bytes] = []
        for key, value in (fields or {}).items():
            chunks.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            )
        if file_bytes is not None:
            chunks.append(
                (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"file\"; filename=\"numeros.txt\"\r\n"
                    f"Content-Type: text/plain\r\n\r\n"
                ).encode()
                + file_bytes
                + b"\r\n"
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        data = b"".join(chunks)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text


def download(url: str) -> bytes:
    headers = {}
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "api.checknumber.ai" or host.endswith(".checknumber.ai"):
        headers["X-API-Key"] = api_key()
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def parse_result_bytes(blob: bytes) -> list[dict]:
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = archive.namelist()
            if any(name.startswith("xl/") for name in names):
                return read_xlsx(blob)
            csv_names = [name for name in names if name.lower().endswith(".csv")]
            if not csv_names:
                raise SystemExit(f"El zip no trae CSV ni xlsx. Archivos: {names[:8]}")
            blob = archive.read(csv_names[0])
    text = blob.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def read_xlsx(blob: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit("El resultado es xlsx. Instalá openpyxl en el venv.") from exc
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = book.active
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell).strip() if cell is not None else "" for cell in next(rows)]
    parsed = []
    for values in rows:
        parsed.append({header[i]: values[i] for i in range(len(header))})
    book.close()
    return parsed


def normalize_results(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        number = row_get(row, "number", "phone", "whatsapp", "phonenumber")
        # "whatsapp" is also the yes/no column on some exports. Prefer number.
        if not number or parse_yes_no(number) is not None:
            number = row_get(row, "number", "phone", "phonenumber")
        digits = to_e164_digits(number) or re.sub(r"\D", "", number)
        activated = parse_yes_no(row_get(row, "activated", "whatsapp"))
        business = parse_yes_no(row_get(row, "business", "whatsapp_business"))
        active_days = parse_int(row_get(row, "activedays", "whatsapp_days", "active_days"))
        out.append(
            {
                "phone": digits,
                "has_whatsapp": activated,
                "is_business": business,
                "active_days": active_days,
            }
        )
    return out


def planned_action(estado: str | None, has_whatsapp: bool | None) -> str:
    estado = (estado or "").strip()
    if has_whatsapp is None:
        return "sin_resultado"
    if estado == "validado":
        return "skip_validado"
    if estado == "no_existente" and has_whatsapp:
        return "skip_meta_no"
    if has_whatsapp:
        return "set_existente"
    return "set_no_existente"


async def fetch_clients(conn, schema: str) -> list[dict]:
    exists = await conn.fetchval(
        "SELECT 1 FROM public.distribuidoras WHERE schema_name = $1",
        schema,
    )
    if not exists:
        raise SystemExit(f"{schema} no está en public.distribuidoras.")
    rows = await conn.fetch(
        f"""
        SELECT id,
               phone_number,
               whatsapp_estado::text AS whatsapp_estado,
               lifecycle::text AS lifecycle
        FROM {schema}.clients
        WHERE phone_number IS NOT NULL
          AND btrim(phone_number) <> ''
        """
    )
    return [dict(row) for row in rows]


async def fetch_provider(conn) -> dict:
    row = await conn.fetchrow(
        """
        SELECT task_type, price_per_check_usd::text AS price, enabled
        FROM core.phone_validation_provider
        WHERE provider_id = $1
        """,
        PROVIDER_ID,
    )
    if not row:
        raise SystemExit("No existe core.phone_validation_provider provider_id=checknumber.")
    provider = dict(row)
    if not provider["enabled"]:
        raise SystemExit("El proveedor checknumber está disabled.")
    if provider["task_type"] != TASK_TYPE:
        raise SystemExit(
            f"core.phone_validation_provider.task_type es {provider['task_type']!r}, se esperaba {TASK_TYPE}."
        )
    return provider


async def fetch_cache(conn, phones: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for offset in range(0, len(phones), 5000):
        chunk = phones[offset : offset + 5000]
        rows = await conn.fetch(
            """
            SELECT phone, has_whatsapp, is_business, active_days, checked_at
            FROM core.phone_whatsapp_check
            WHERE phone = ANY($1::text[])
            """,
            chunk,
        )
        for row in rows:
            found[row["phone"]] = dict(row)
    return found


def cache_fresh(row: dict, now: datetime) -> bool:
    checked = row.get("checked_at")
    if checked is None:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    ttl = YES_TTL if row.get("has_whatsapp") else NO_TTL
    return now - checked <= ttl


def cmd_extraer(schema: str) -> None:
    import asyncio

    async def run():
        conn = await connect()
        try:
            provider = await fetch_provider(conn)
            clients = await fetch_clients(conn, schema)
            grouped: dict[str, list[dict]] = {}
            invalid = []
            for client in clients:
                digits = to_e164_digits(client["phone_number"])
                if not digits:
                    invalid.append(client)
                    continue
                grouped.setdefault(digits, []).append(client)
            cache = await fetch_cache(conn, list(grouped))
        finally:
            await conn.close()

        now = datetime.now(timezone.utc)
        fresh = {phone: row for phone, row in cache.items() if cache_fresh(row, now)}
        to_send = sorted(phone for phone in grouped if phone not in fresh)
        price = Decimal(provider["price"])
        estimate = (price * len(to_send)).quantize(Decimal("0.000001"))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = lote_dir(schema, stamp)
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "input.txt").write_text(
            "".join(f"+{phone}\n" for phone in to_send),
            encoding="utf-8",
        )
        with (folder / "invalidos.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["client_id", "phone_number", "lifecycle"])
            writer.writeheader()
            for client in invalid:
                writer.writerow(
                    {
                        "client_id": client["id"],
                        "phone_number": client["phone_number"],
                        "lifecycle": client.get("lifecycle") or "",
                    }
                )
        with (folder / "cache.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["phone", "has_whatsapp", "is_business", "active_days", "checked_at"],
            )
            writer.writeheader()
            for phone, row in sorted(fresh.items()):
                writer.writerow(
                    {
                        "phone": phone,
                        "has_whatsapp": row.get("has_whatsapp"),
                        "is_business": row.get("is_business"),
                        "active_days": row.get("active_days"),
                        "checked_at": row.get("checked_at"),
                    }
                )
        resumen = {
            "schema": schema,
            "clientes_con_telefono": len(clients),
            "unicos_validos": len(grouped),
            "invalidos": len(invalid),
            "cache_vigente": len(fresh),
            "a_enviar": len(to_send),
            "precio_usd": str(price),
            "costo_estimado_usd": str(estimate),
            "task_type": TASK_TYPE,
            "lote": str(folder),
        }
        write_json(folder / "resumen.json", resumen)
        print(json.dumps(resumen, ensure_ascii=False, indent=2))

    asyncio.run(run())


def cmd_enviar(schema: str, lote: str | None, confirmar: bool) -> None:
    folder = Path(lote) if lote else lote_dir(schema)
    resumen = read_json(folder / "resumen.json")
    if (folder / "task.json").exists():
        task = read_json(folder / "task.json")
        raise SystemExit(
            f"Este lote ya tiene task_id={task.get('task_id')}. Corré bajar. No se reenvía."
        )
    if not confirmar:
        raise SystemExit("Falta --confirmar. No se envió nada a checknumber.ai.")
    input_path = folder / "input.txt"
    phones = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not phones:
        raise SystemExit("input.txt está vacío. No hay nada que enviar.")
    status, balance_body = api_request("GET", "/v1/balance", timeout=30)
    if status != 200 or not isinstance(balance_body, dict) or "balance" not in balance_body:
        raise SystemExit(f"No se pudo leer el saldo ({status}): {balance_body}")
    balance = Decimal(str(balance_body["balance"]))
    estimate = Decimal(resumen["costo_estimado_usd"])
    print(json.dumps({"saldo": str(balance), "costo_estimado_usd": str(estimate), "a_enviar": len(phones)}, indent=2))
    if balance < estimate:
        raise SystemExit("El saldo es menor que el costo estimado. No se creó la tarea.")
    code, body = api_request(
        "POST",
        "/v1/tasks",
        fields={"task_type": TASK_TYPE},
        file_bytes=input_path.read_bytes(),
        timeout=120,
    )
    write_json(folder / "submit.json", {"http_status": code, "body": body})
    if code not in (200, 202) or not isinstance(body, dict) or not body.get("task_id"):
        raise SystemExit(
            f"checknumber no creó la tarea ({code}). No reintentar el POST: puede haber cobrado. Body en submit.json."
        )
    write_json(
        folder / "task.json",
        {"task_id": body["task_id"], "status": body.get("status"), "submit": body},
    )
    print(json.dumps({"task_id": body["task_id"], "status": body.get("status"), "lote": str(folder)}, indent=2))


def cmd_bajar(schema: str, lote: str | None) -> None:
    folder = Path(lote) if lote else lote_dir(schema)
    task = read_json(folder / "task.json")
    task_id = task["task_id"]
    deadline = time.time() + POLL_DEADLINE_S
    delay = 5
    body: dict | str = {}
    while True:
        code, body = api_request("POST", "/v1/gettasks", fields={"task_id": task_id}, timeout=60)
        if code != 200 or not isinstance(body, dict):
            raise SystemExit(f"gettasks falló ({code}): {body}")
        task["status"] = body.get("status")
        task["last_poll"] = body
        write_json(folder / "task.json", task)
        status = body.get("status")
        print(json.dumps({"status": status, "success": body.get("success"), "failure": body.get("failure"), "total": body.get("total")}))
        if status == "exported":
            break
        if status == "failed":
            raise SystemExit("La tarea quedó failed. No se cobra un reintento automático.")
        if time.time() > deadline:
            raise SystemExit("Pasaron 15 minutos. Volvé a correr bajar con el mismo lote.")
        time.sleep(delay)
        delay = min(delay + 5, 20)
    result_url = body.get("result_url")
    if not result_url:
        raise SystemExit("status=exported pero no hay result_url.")
    blob = download(result_url)
    (folder / "resultado.bin").write_bytes(blob)
    parsed = normalize_results(parse_result_bytes(blob))
    with (folder / "resultados.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["phone", "has_whatsapp", "is_business", "active_days"])
        writer.writeheader()
        writer.writerows(parsed)
    yes = sum(1 for row in parsed if row["has_whatsapp"] is True)
    no = sum(1 for row in parsed if row["has_whatsapp"] is False)
    missing = sum(1 for row in parsed if row["has_whatsapp"] is None)
    actual = body.get("actual_amount")
    summary = {
        "filas": len(parsed),
        "whatsapp_si": yes,
        "whatsapp_no": no,
        "sin_resultado": missing,
        "actual_amount": actual,
        "lote": str(folder),
    }
    write_json(folder / "resultados-resumen.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def cmd_aplicar(schema: str, lote: str | None, confirmar: bool) -> None:
    import asyncio

    folder = Path(lote) if lote else lote_dir(schema)
    results: dict[str, dict] = {}
    fresh: dict[str, dict] = {}
    cache_path = folder / "cache.csv"
    if cache_path.exists():
        with cache_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("phone"):
                    results[row["phone"]] = row
    results_path = folder / "resultados.csv"
    if results_path.exists():
        with results_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("phone"):
                    fresh[row["phone"]] = row
                    results[row["phone"]] = row
    if not results:
        raise SystemExit("No hay cache.csv ni resultados.csv en el lote.")

    async def run():
        conn = await connect()
        try:
            clients = await fetch_clients(conn, schema)
            preview = []
            for client in clients:
                digits = to_e164_digits(client["phone_number"])
                result = results.get(digits or "")
                if not digits or not result:
                    continue
                has_whatsapp = parse_yes_no(result.get("has_whatsapp"))
                action = planned_action(client.get("whatsapp_estado"), has_whatsapp)
                preview.append(
                    {
                        "client_id": client["id"],
                        "phone": digits,
                        "whatsapp_estado_prev": client.get("whatsapp_estado") or "",
                        "accion": action,
                        "has_whatsapp": result.get("has_whatsapp") or "",
                        "is_business": result.get("is_business") or "",
                        "active_days": result.get("active_days") or "",
                    }
                )
            with (folder / "aplicar-preview.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(preview[0].keys()) if preview else ["client_id"])
                writer.writeheader()
                writer.writerows(preview)
            counts: dict[str, int] = {}
            for row in preview:
                counts[row["accion"]] = counts.get(row["accion"], 0) + 1
            print(json.dumps({"preview": counts, "lote": str(folder)}, ensure_ascii=False, indent=2))
            if not confirmar:
                print("Sin --confirmar no se escribió la base.")
                return
            now = datetime.now(timezone.utc)
            cache_rows = []
            for phone, result in fresh.items():
                has_whatsapp = parse_yes_no(result.get("has_whatsapp"))
                if not phone or has_whatsapp is None:
                    continue
                cache_rows.append(
                    (
                        phone,
                        has_whatsapp,
                        parse_yes_no(result.get("is_business")),
                        parse_int(result.get("active_days")),
                    )
                )
            async with conn.transaction():
                if cache_rows:
                    await conn.executemany(
                        """
                        INSERT INTO core.phone_whatsapp_check
                            (phone, has_whatsapp, is_business, active_days, provider_id, checked_at)
                        VALUES ($1, $2, $3, $4, 'checknumber', $5)
                        ON CONFLICT (phone) DO UPDATE SET
                            has_whatsapp = EXCLUDED.has_whatsapp,
                            is_business = EXCLUDED.is_business,
                            active_days = EXCLUDED.active_days,
                            provider_id = EXCLUDED.provider_id,
                            checked_at = EXCLUDED.checked_at
                        """,
                        [(phone, has_wa, business, days, now) for phone, has_wa, business, days in cache_rows],
                    )
                updates = []
                for row in preview:
                    if row["accion"] == "set_existente":
                        updates.append((row["client_id"], "existente"))
                    elif row["accion"] == "set_no_existente":
                        updates.append((row["client_id"], "no_existente"))
                if updates:
                    await conn.executemany(
                    f"""
                    UPDATE {schema}.clients
                    SET whatsapp_estado = $2::core.whatsapp_estado_cliente_enum,
                        whatsapp_existencia_verificada_at = $3
                    WHERE id = $1
                      AND whatsapp_estado IS DISTINCT FROM 'validado'
                      AND NOT (whatsapp_estado = 'no_existente' AND $2::text = 'existente')
                    """,
                    [(client_id, estado, now) for client_id, estado in updates],
                )
            write_json(
                folder / "aplicar-log.json",
                {"aplicado_at": now.isoformat(), "cache": len(cache_rows), "clients": len(updates), "preview": counts},
            )
            print(json.dumps({"cache": len(cache_rows), "clients_actualizados": len(updates)}, indent=2))
        finally:
            await conn.close()

    asyncio.run(run())


def cmd_self_test() -> None:
    cases = {
        "+54 9 351 555-1234": "5493515551234",
        "5493515551234": "5493515551234",
        "03515551234": "543515551234",
        "93515551234": "5493515551234",
        "3515551234": "543515551234",
        "12125551234": "12125551234",
        "54911": None,
        "": None,
        "123": None,
        "005491155556666": "5491155556666",
    }
    failed = 0
    for raw, expected in cases.items():
        got = to_e164_digits(raw)
        if got != expected:
            print(f"FAIL {raw!r} -> {got!r}, esperado {expected!r}")
            failed += 1
    actions = [
        ("validado", True, "skip_validado"),
        ("validado", False, "skip_validado"),
        ("no_existente", True, "skip_meta_no"),
        ("no_existente", False, "set_no_existente"),
        ("no_validado", True, "set_existente"),
        ("existente", False, "set_no_existente"),
        (None, None, "sin_resultado"),
    ]
    for estado, has, expected in actions:
        got = planned_action(estado, has)
        if got != expected:
            print(f"FAIL accion {estado} {has} -> {got}, esperado {expected}")
            failed += 1
    if failed:
        raise SystemExit(f"{failed} asserts fallaron")
    print("self-test ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validar teléfonos de una distribuidora con checknumber.ai")
    sub = parser.add_subparsers(dest="fase", required=True)
    for name in ("extraer", "enviar", "bajar", "aplicar"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--schema", required=True)
        if name != "extraer":
            cmd.add_argument("--lote")
        if name in ("enviar", "aplicar"):
            cmd.add_argument("--confirmar", action="store_true")
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.fase == "self-test":
        cmd_self_test()
        return
    schema = require_schema(args.schema)
    if args.fase == "extraer":
        cmd_extraer(schema)
    elif args.fase == "enviar":
        cmd_enviar(schema, args.lote, args.confirmar)
    elif args.fase == "bajar":
        cmd_bajar(schema, args.lote)
    elif args.fase == "aplicar":
        cmd_aplicar(schema, args.lote, args.confirmar)


if __name__ == "__main__":
    main()
