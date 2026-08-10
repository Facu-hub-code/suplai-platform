#!/usr/bin/env python3
"""Geocodifica clientes de dimer con Google Maps Geocoding API (Chile).

Uso:
  set -a && source ../backend-supabase/.env && set +a
  # dry-run (CSV + muestra):
  python scripts/dimer/geocode_clientes.py
  # aplicar a BD:
  python scripts/dimer/geocode_clientes.py --apply
  # prueba chica:
  python scripts/dimer/geocode_clientes.py --limit 20 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "dimer"
CITY_HINT = "Valparaíso, Chile"
REGION = "cl"
COUNTRY = "CL"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SSL_CTX = ssl._create_unverified_context()


def _db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "").strip()
    if not url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL")
    # Forzar pooler transaction mode (6543) si alguien pasó session mode
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def _api_key() -> str:
    key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("[FAIL] Falta GOOGLE_MAPS_API_KEY")
    return key


def build_query(direccion: str) -> str:
    d = (direccion or "").strip()
    low = d.lower()
    if "chile" in low or "valpara" in low or "viña" in low or "vina" in low:
        return d
    return f"{d}, {CITY_HINT}"


def geocode(address: str, api_key: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "address": address,
            "region": REGION,
            "components": f"country:{COUNTRY}",
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "SuplaiDimerGeocode/1.0"})
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
        data = json.load(resp)

    status = str(data.get("status") or "")
    if status != "OK" or not data.get("results"):
        return {
            "ok": False,
            "status": status,
            "error_message": data.get("error_message"),
            "lat": None,
            "lng": None,
            "formatted": None,
            "location_type": None,
        }

    first = data["results"][0]
    geom = first.get("geometry") or {}
    loc = geom.get("location") or {}
    return {
        "ok": True,
        "status": status,
        "error_message": None,
        "lat": float(loc["lat"]),
        "lng": float(loc["lng"]),
        "formatted": first.get("formatted_address"),
        "location_type": geom.get("location_type"),
        "partial_match": bool(first.get("partial_match")),
    }


async def main() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv()

    parser = argparse.ArgumentParser(description="Geocodificar clientes dimer (Chile)")
    parser.add_argument("--apply", action="store_true", help="Escribir en client_locations")
    parser.add_argument("--limit", type=int, default=0, help="Limitar cantidad a procesar")
    parser.add_argument("--sleep", type=float, default=0.12, help="Delay entre requests (s)")
    parser.add_argument(
        "--clean-orphans",
        action="store_true",
        help="Borrar ubicaciones huérfanas (client_id sin cliente)",
    )
    args = parser.parse_args()

    api_key = _api_key()
    db_url = _db_url()
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "phase-04-geocode-clientes.csv"

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        if args.clean_orphans or args.apply:
            deleted = await conn.fetchval(
                f"""
                WITH d AS (
                  DELETE FROM {SCHEMA}.client_locations cl
                  WHERE NOT EXISTS (
                    SELECT 1 FROM {SCHEMA}.clients c WHERE c.id = cl.client_id
                  )
                  RETURNING 1
                )
                SELECT COUNT(*) FROM d
                """
            )
            print(f"[*] Ubicaciones huérfanas eliminadas: {deleted}")

        rows = await conn.fetch(
            f"""
            SELECT c.id, c.razon_social, c.nombre, c.direccion
            FROM {SCHEMA}.clients c
            WHERE COALESCE(TRIM(c.direccion), '') <> ''
              AND NOT EXISTS (
                SELECT 1
                FROM {SCHEMA}.client_locations cl
                WHERE cl.client_id = c.id
                  AND cl.latitude IS NOT NULL
                  AND cl.longitude IS NOT NULL
              )
            ORDER BY c.id
            """
        )
        if args.limit and args.limit > 0:
            rows = rows[: args.limit]

        print(f"[*] Clientes a geocodificar: {len(rows)}")
        results = []
        ok_n = fail_n = 0

        for i, row in enumerate(rows, 1):
            query = build_query(row["direccion"])
            print(f"[{i}/{len(rows)}] id={row['id']} → {query[:90]}")
            try:
                geo = geocode(query, api_key)
            except Exception as exc:
                geo = {
                    "ok": False,
                    "status": "HTTP_ERROR",
                    "error_message": str(exc),
                    "lat": None,
                    "lng": None,
                    "formatted": None,
                    "location_type": None,
                    "partial_match": None,
                }

            rec = {
                "client_id": row["id"],
                "razon_social": row["razon_social"] or row["nombre"],
                "direccion": row["direccion"],
                "query": query,
                "ok": geo["ok"],
                "status": geo.get("status"),
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
                "formatted": geo.get("formatted"),
                "location_type": geo.get("location_type"),
                "partial_match": geo.get("partial_match"),
                "error_message": geo.get("error_message"),
            }
            results.append(rec)
            if geo["ok"]:
                ok_n += 1
                print(
                    f"  OK {geo['location_type']} ({geo['lat']:.6f},{geo['lng']:.6f}) "
                    f"{(geo.get('formatted') or '')[:70]}"
                )
            else:
                fail_n += 1
                print(f"  FAIL {geo.get('status')} {geo.get('error_message')}")

            time.sleep(args.sleep)

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "client_id",
                    "razon_social",
                    "direccion",
                    "query",
                    "ok",
                    "status",
                    "lat",
                    "lng",
                    "formatted",
                    "location_type",
                    "partial_match",
                    "error_message",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        print(f"[*] CSV: {csv_path}")
        print(f"[*] OK={ok_n} FAIL={fail_n}")

        if not args.apply:
            print("[*] Dry-run. Re-ejecutá con --apply para escribir en BD.")
            return

        applied = 0
        for rec in results:
            if not rec["ok"] or rec["lat"] is None or rec["lng"] is None:
                continue
            lat = float(rec["lat"])
            lng = float(rec["lng"])
            conf = 0.9 if rec.get("location_type") == "ROOFTOP" else 0.7
            if rec.get("partial_match"):
                conf = min(conf, 0.55)

            existing = await conn.fetchval(
                f"""
                SELECT id FROM {SCHEMA}.client_locations
                WHERE client_id = $1 AND COALESCE(is_primary, true)
                ORDER BY id
                LIMIT 1
                """,
                rec["client_id"],
            )
            if existing:
                await conn.execute(
                    f"""
                    UPDATE {SCHEMA}.client_locations
                    SET source = 'manual_text',
                        latitude = $2,
                        longitude = $3,
                        location = extensions.ST_SetSRID(extensions.ST_MakePoint($3, $2), 4326),
                        address_text = $4,
                        geocode_status = 'resolved',
                        confidence = $5,
                        is_primary = true,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    existing,
                    lat,
                    lng,
                    rec.get("formatted") or rec["direccion"],
                    conf,
                )
            else:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.client_locations
                      (client_id, source, latitude, longitude, location,
                       address_text, geocode_status, confidence, is_primary, created_by)
                    VALUES (
                      $1, 'manual_text', $2, $3,
                      extensions.ST_SetSRID(extensions.ST_MakePoint($3, $2), 4326),
                      $4, 'resolved', $5, true, 'scripts/dimer/geocode_clientes.py'
                    )
                    """,
                    rec["client_id"],
                    lat,
                    lng,
                    rec.get("formatted") or rec["direccion"],
                    conf,
                )
            applied += 1

        total_locs = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.client_locations")
        with_coords = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {SCHEMA}.client_locations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        )
        print(f"[*] Aplicados: {applied}")
        print(f"[*] client_locations total={total_locs} con_coords={with_coords}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
