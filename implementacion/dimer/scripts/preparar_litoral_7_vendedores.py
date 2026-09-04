#!/usr/bin/env python3
"""Genera CSVs de la propuesta Litoral 7 vendedores (sin escribir en BD)."""
from __future__ import annotations

import csv
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
XLSX = ROOT / "inputs" / "Propuesta Litoral 7 Vendedores.xlsx"

VENDEDORES = [
    {"codigo_ruta": "9", "territorio": "Casablanca / Algarrobo", "nombre": "Gustavo López", "telefono": "56964037193", "rol": "vendedor", "es_territorio_nuevo": False},
    {"codigo_ruta": "NUEVO2", "territorio": "El Quisco / Isla Negra", "nombre": "José Quero", "telefono": "56961816090", "rol": "vendedor", "es_territorio_nuevo": True},
    {"codigo_ruta": "28", "territorio": "El Tabo / Cartagena", "nombre": "Doralisa Vivencio", "telefono": "56979888434", "rol": "vendedor", "es_territorio_nuevo": False},
    {"codigo_ruta": "NUEVO1", "territorio": "San Antonio Norte", "nombre": "Natalia Martinez", "telefono": "56958141749", "rol": "vendedor", "es_territorio_nuevo": True},
    {"codigo_ruta": "29", "territorio": "San Antonio Sur / Sto. Domingo", "nombre": "Maryvonne Zárate", "telefono": "56964636942", "rol": "vendedor", "es_territorio_nuevo": False},
    {"codigo_ruta": "30", "territorio": "Melipilla", "nombre": "María Verónica Montes", "telefono": "56958142220", "rol": "vendedor", "es_territorio_nuevo": False},
    {"codigo_ruta": "31", "territorio": "Curacavi / Maria Pinto", "nombre": "Luis Torrealba", "telefono": "56958146252", "rol": "vendedor", "es_territorio_nuevo": False},
    {"codigo_ruta": "JZ", "territorio": "Litoral", "nombre": "Francisco Diaz", "telefono": "56961916961", "rol": "jefe_zonal", "es_territorio_nuevo": False},
]

TERR_MAP = {
    "9 - Casablanca / Algarrobo": "9",
    "NUEVO 2 - El Quisco / Isla Negra": "NUEVO2",
    "28 - El Tabo / Cartagena": "28",
    "NUEVO 1 - San Antonio Norte": "NUEVO1",
    "29 - San Antonio Sur / Sto. Domingo": "29",
    "30 - Melipilla": "30",
    "31 - Curacavi/Maria Pinto": "31",
}


def digits(s: object) -> str:
    return re.sub(r"[^0-9]", "", str(s or ""))


def mobile_key(s: object) -> str:
    d = digits(s)
    if len(d) >= 9 and d[-9] == "9":
        return d[-9:]
    return ""


def is_fake(s: object) -> bool:
    d = digits(s)
    return d in {"555555555", "56555555555", "5555555555", "5655555555"} or (
        len(d) >= 8 and set(d) <= {"5"}
    )


def load_dimer_phones(path: Path) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = mobile_key(row.get("phone") or "")
            if k and k not in by_key:
                by_key[k] = row
    return by_key


def main() -> None:
    snapshot = OUT / "litoral-dimer-phones-snapshot.csv"
    dimer_by_key = load_dimer_phones(snapshot) if snapshot.exists() else {}
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["Detalle completo"]
    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        rut, razon, tel, dir_, comuna, sector, vend_act, vend_prop, cambia, dias, venta, ignamar = row[1:13]
        if not rut and not razon:
            continue
        tel_s = tel.strip() if isinstance(tel, str) else (str(int(tel)) if isinstance(tel, (int, float)) and tel else "")
        razon_s = razon.strip() if isinstance(razon, str) else str(razon or "")
        dir_s = dir_.strip() if isinstance(dir_, str) else str(dir_ or "")
        k = mobile_key(tel_s) if tel_s and not is_fake(tel_s) else ""
        hit = dimer_by_key.get(k) if k else None
        codigo = TERR_MAP.get(str(vend_prop or "").strip(), "")
        vend = next((v for v in VENDEDORES if v["codigo_ruta"] == codigo), None)
        if hit:
            match = "en_dimer"
        elif k:
            match = "nuevo_con_whatsapp"
        elif tel_s and not is_fake(tel_s):
            match = "tel_no_movil"
        else:
            match = "sin_telefono"
        rows.append({
            "excel_row": i,
            "rut": str(rut).strip() if rut else "",
            "razon_social": razon_s,
            "telefono_excel": tel_s,
            "telefono_norm": ("56" + k) if k else "",
            "mobile_key": k,
            "direccion": dir_s,
            "comuna": comuna or "",
            "sector": sector or "",
            "vendedor_actual": vend_act or "",
            "vendedor_propuesto": vend_prop or "",
            "codigo_ruta": codigo,
            "vendedor_nombre": vend["nombre"] if vend else "",
            "vendedor_telefono": vend["telefono"] if vend else "",
            "jefe_zonal_nombre": "Francisco Diaz",
            "jefe_zonal_telefono": "56961916961",
            "cambia": str(cambia or "").strip().upper(),
            "dias_visita": dias or "",
            "venta_verano": venta or 0,
            "ignamar_verano": ignamar or "",
            "match": match,
            "client_id": hit.get("id", "") if hit else "",
            "dimer_nombre": hit.get("nombre", "") if hit else "",
            "dimer_phone": hit.get("phone", "") if hit else "",
            "wa_elegible": "si" if k else "no",
        })

    OUT.mkdir(exist_ok=True)
    with (OUT / "litoral-vendedores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_ruta", "territorio", "nombre", "telefono", "rol", "es_territorio_nuevo", "is_mock"])
        w.writeheader()
        for v in VENDEDORES:
            w.writerow({**v, "is_mock": False})

    with (OUT / "litoral-cartera.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    best: dict[str, tuple] = {}
    for r in rows:
        if r["wa_elegible"] != "si":
            continue
        k = r["mobile_key"]
        score = (1 if r["cambia"] == "SI" else 0, float(r["venta_verano"] or 0))
        prev = best.get(k)
        if not prev or score > prev[0]:
            best[k] = (score, r)

    wa_rows = []
    for k, (_, r) in best.items():
        sharing = sum(1 for x in rows if x["mobile_key"] == k)
        wa_rows.append({
            "telefono": r["telefono_norm"],
            "mobile_key": k,
            "client_id": r["client_id"],
            "rut": r["rut"],
            "razon_social": r["razon_social"],
            "comuna": r["comuna"],
            "codigo_ruta": r["codigo_ruta"],
            "vendedor_nombre": r["vendedor_nombre"],
            "vendedor_telefono": r["vendedor_telefono"],
            "jefe_zonal_nombre": r["jefe_zonal_nombre"],
            "jefe_zonal_telefono": r["jefe_zonal_telefono"],
            "cambia": r["cambia"],
            "match": r["match"],
            "pdvs_mismo_telefono": sharing,
            "accion": "asignar_existente" if r["client_id"] else "crear_cliente_y_enviar",
        })
    wa_rows.sort(key=lambda x: (x["codigo_ruta"], x["razon_social"]))
    with (OUT / "litoral-destinatarios-whatsapp.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(wa_rows[0].keys()))
        w.writeheader()
        w.writerows(wa_rows)

    print(f"cartera={len(rows)} wa_unicos={len(wa_rows)} en_dimer={sum(1 for r in wa_rows if r['client_id'])}")


if __name__ == "__main__":
    main()
