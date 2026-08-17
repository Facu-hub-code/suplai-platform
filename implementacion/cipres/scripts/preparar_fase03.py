#!/usr/bin/env python3
"""Fase 3 cipres — cross/up-sell heurístico (catálogo grande, sin IA)."""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "outputs"

CROSS_SELL = [
    ("CIP-0026", "CIP-0132", "Complementá el aerosol Saphirus con un aromatizador deco de la misma línea."),
    ("CIP-0025", "CIP-0852", "Cross-sell marca líder: sumá sahumerios para ambientes más duraderos."),
    ("CIP-0128", "CIP-0026", "Cross-sell Saphirus: antihumedad + aerosol para baño y ambientes."),
    ("CIP-0001", "CIP-2424", "Desinfectante Cipclor + microfibra para pisos: kit básico de limpieza."),
    ("CIP-1711", "CIP-1741", "Lavavajillas Ala + dispenser con esponja para cocina."),
    ("CIP-1024", "CIP-0003", "Shampoo y acondicionador Algabo aguacate: rutina de cabello completa."),
    ("CIP-1068", "CIP-1776", "Detergente Woolite + suavizante Ecovita para lavado de ropa."),
    ("CIP-0828", "CIP-0829", "Raid aerosol + aparato 45 noches: protección antimosquitos integral."),
    ("CIP-0127", "CIP-0024", "Alguicida Cipclor + acople Vulcano para mantenimiento de pileta."),
    ("CIP-1587", "CIP-1900", "Desengrasante de cocina + extracto concentrado para uso profesional."),
    ("CIP-0454", "CIP-0254", "Esferas aromáticas Aromanza + difusor para auto."),
    ("CIP-0022", "CIP-0849", "Accesorios Vulcano: acople + rejilla superior para pileta."),
]

UP_SELL = [
    ("CIP-0001", "CIP-0002", "Pasá al formato 5 L de Cipclor: mejor rendimiento para comercios."),
    ("CIP-0128", "CIP-0129", "Antihumedad Saphirus 285 g: mayor duración en baños y placards."),
    ("CIP-0129", "CIP-0130", "Antihumedad Saphirus 385 g: formato premium de la línea."),
    ("CIP-1587", "CIP-1588", "Desengrasante de cocina 5 L: ahorro para uso frecuente."),
    ("CIP-1555", "CIP-1554", "Crema desengrasante Jarama 1 kg: formato mayor para taller o cocina."),
    ("CIP-1776", "CIP-1778", "Suavizante Ecovita 3 L: mejor precio por litro."),
    ("CIP-1024", "CIP-1022", "Shampoo Algabo Baby 444 cc: formato familiar con mejor rendimiento."),
    ("CIP-0127", "CIP-0002", "Cipclor 5 L para tratamiento completo de pileta."),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cross_path = OUT / "phase-03-cross-sell.csv"
    up_path = OUT / "phase-03-up-sell.csv"

    for path, rows in ((cross_path, CROSS_SELL), (up_path, UP_SELL)):
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["base_product_code", "related_product_code", "reason", "is_mock"])
            for base, related, reason in rows:
                w.writerow([base, related, reason, "true"])
        print(f"[+] {path.name}: {len(rows)} filas")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
