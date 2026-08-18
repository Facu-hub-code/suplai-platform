"""Tests unitarios del matcher de productos y teléfono (sin BD)."""

from __future__ import annotations

from funnel_campi import (
    classify_canal,
    estado_grupo,
    fold_text,
    line_mentioned_in_corpus,
    match_ratio_for_lines,
    motivo_exclusion,
    phone_match_key,
    tokenize_product_name,
)


def test_phone_match_key_last10():
    assert phone_match_key("+54 9 351 123-4567") == "3511234567"
    assert phone_match_key("5493511234567") == "3511234567"
    assert phone_match_key("3511234567") == "3511234567"
    assert phone_match_key("123") == "123"


def test_fold_and_tokens():
    assert "crema" in tokenize_product_name("Crema de Leche La Serenísima")
    assert "de" not in tokenize_product_name("Crema de Leche")
    assert fold_text("PÉSIMO") == "pesimo"


def test_line_mentioned_by_code_and_name():
    corpus = "hola, me pasas 2 coca cola 2.25 y el codigo 15002"
    assert line_mentioned_in_corpus("15002", "Coca Cola 2.25", corpus)
    assert line_mentioned_in_corpus("99999", "Coca Cola 2.25", corpus)
    assert line_mentioned_in_corpus("99999", "Aceite Cañuelas 900", "seis aceites canuelas de un litro")


def test_match_ratio():
    lines = [
        {"product_code": "A1", "nombre": "Agua Mineral Villavicencio"},
        {"product_code": "B2", "nombre": "Fernet Branca 750"},
    ]
    corpus = "mandame agua mineral villavicencio"
    ratio, matched, unmatched = match_ratio_for_lines(lines, corpus)
    assert matched == ["A1"]
    assert unmatched == ["B2"]
    assert ratio == 0.5


def test_motivo_and_estado_and_canal():
    assert motivo_exclusion(origen="erp", tiene_inbound=True, en_ventana=True, fecha_medianoche=False) == "origen_erp"
    assert motivo_exclusion(origen="suplai", tiene_inbound=False, en_ventana=False, fecha_medianoche=False) == "sin_conversacion"
    assert motivo_exclusion(origen="suplai", tiene_inbound=True, en_ventana=False, fecha_medianoche=False) == "fuera_de_ventana"
    assert motivo_exclusion(origen="suplai", tiene_inbound=True, en_ventana=True, fecha_medianoche=True) == "carga_historica_sin_hora"
    assert motivo_exclusion(origen="suplai", tiene_inbound=True, en_ventana=True, fecha_medianoche=False) == ""
    assert estado_grupo("confirmado") == "cerrado"
    assert estado_grupo("descargado") == "cerrado"
    assert estado_grupo("abierto") == "abierto"
    canal, has_url = classify_canal("suplai", "mirá https://tienda.suplaisales.com/del_corro?wp=1")
    assert canal == "tienda" and has_url
    canal2, has_url2 = classify_canal("suplai", "mandame 3 coca")
    assert canal2 == "chat" and not has_url2
    canal3, _ = classify_canal("tienda", "hola")
    assert canal3 == "tienda"


if __name__ == "__main__":
    test_phone_match_key_last10()
    test_fold_and_tokens()
    test_line_mentioned_by_code_and_name()
    test_match_ratio()
    test_motivo_and_estado_and_canal()
    print("ok")
