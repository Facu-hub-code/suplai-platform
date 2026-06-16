"""
Carga y expansión de casos E2E basados en fixtures reales del distribuidor.

Estructura esperada:
  implementacion/{schema}/casos-reales/
    manifest.json
    contexto.md
    casos/{slug}/caso.json
    casos/{slug}/mensaje.txt | mensaje_simulado.txt
    casos/{slug}/imagen.* (opcional, referencia; E2E usa mensaje_simulado si existe)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTACION = ROOT / "implementacion"

IMAGE_PREFIX = "[Consulta con foto por WhatsApp]"


def real_cases_root(schema: str) -> Path:
    return IMPLEMENTACION / schema / "casos-reales"


def load_manifest(schema: str) -> dict[str, Any]:
    path = real_cases_root(schema) / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No existe {path}. Creá la carpeta casos-reales con manifest.json (ver skill agent-e2e-testing)."
        )
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"manifest.json inválido en {path}")
    return data


def load_context(schema: str) -> str:
    manifest = load_manifest(schema)
    rel = manifest.get("context_file") or "contexto.md"
    path = real_cases_root(schema) / rel
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _read_message_file(case_dir: Path, fname: str) -> str:
    p = case_dir / fname
    if not p.is_file():
        raise ValueError(f"Archivo de mensaje no encontrado: {p}")
    return p.read_text(encoding="utf-8").strip()


def _read_message(case_dir: Path, spec: dict[str, Any]) -> str:
    if spec.get("message"):
        return str(spec["message"]).strip()
    for key in ("message_file", "mensaje_file"):
        fname = spec.get(key)
        if fname:
            return _read_message_file(case_dir, fname)
    for candidate in ("mensaje_simulado.txt", "mensaje.txt", "message.txt"):
        p = case_dir / candidate
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    raise ValueError(f"Sin mensaje en {case_dir} (message, message_file o mensaje.txt)")


def _read_products_message(case_dir: Path, spec: dict[str, Any]) -> str | None:
    if spec.get("message_products"):
        return str(spec["message_products"]).strip()
    fname = spec.get("message_products_file")
    if fname:
        return _read_message_file(case_dir, fname)
    for candidate in ("mensaje_productos.txt",):
        p = case_dir / candidate
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    return None


def _normalize_case(spec: dict[str, Any], case_dir: Path, *, idx: int) -> dict[str, Any]:
    message = _read_message(case_dir, spec)
    image_files = sorted(
        p.name
        for p in case_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    )
    if image_files and not message.startswith(IMAGE_PREFIX):
        # Si hay imagen de referencia pero el mensaje no simula visión, lo marcamos en metadata.
        pass

    case_id = spec.get("id", idx)
    if isinstance(case_id, str) and case_id.isdigit():
        case_id = int(case_id)

    message_products = _read_products_message(case_dir, spec)

    return {
        "id": case_id,
        "name": spec.get("name") or case_dir.name,
        "message": message,
        "message_products": message_products,
        "expected_skus": list(spec.get("expected_skus") or []),
        "expected_behavior": (spec.get("expected_behavior") or "").strip(),
        "expected_behavior_products": (spec.get("expected_behavior_products") or "").strip(),
        "expected_tools": list(spec.get("expected_tools") or []),
        "expected_tools_any": list(spec.get("expected_tools_any") or []),
        "expected_tools_products": list(spec.get("expected_tools_products") or []),
        "expected_tools_products_any": list(spec.get("expected_tools_products_any") or []),
        "client_identifier": spec.get("client_identifier"),
        "client_id": spec.get("client_id"),
        "client_alias_recommended": spec.get("client_alias_recommended"),
        "expected_skus_out_of_stock": list(spec.get("expected_skus_out_of_stock") or []),
        "sender_phone": spec.get("sender_phone"),
        "source": spec.get("source") or "real",
        "slug": spec.get("slug") or case_dir.name,
        "tags": list(spec.get("tags") or []),
        "fixture_dir": str(case_dir.relative_to(ROOT)),
        "reference_images": image_files,
        "sequential_order": spec.get("sequential_order", idx),
    }


def list_real_case_dirs(schema: str) -> list[Path]:
    casos_dir = real_cases_root(schema) / "casos"
    if not casos_dir.is_dir():
        return []
    return sorted(
        [p for p in casos_dir.iterdir() if p.is_dir() and (p / "caso.json").is_file()],
        key=lambda p: p.name,
    )


def load_real_cases(schema: str) -> list[dict[str, Any]]:
    dirs = list_real_case_dirs(schema)
    if not dirs:
        raise FileNotFoundError(
            f"No hay casos en {real_cases_root(schema) / 'casos'}/*/caso.json"
        )
    cases: list[dict[str, Any]] = []
    for i, case_dir in enumerate(dirs, start=1):
        with (case_dir / "caso.json").open(encoding="utf-8") as f:
            spec = json.load(f)
        cases.append(_normalize_case(spec, case_dir, idx=i))
    cases.sort(key=lambda c: (c.get("sequential_order", c["id"]), c["id"]))
    for i, c in enumerate(cases, start=1):
        c["id"] = i
    return cases


def validate_real_cases(
    test_cases: list[dict[str, Any]],
    valid_skus: set[str],
    valid_tools: set[str],
    *,
    products_only: bool = False,
) -> list[str]:
    errors: list[str] = []
    for case in test_cases:
        prefix = f"Caso real [{case.get('slug', case.get('id'))}]:"
        if products_only:
            if not case.get("message_products"):
                errors.append(f"{prefix} falta mensaje_productos (message_products_file o mensaje_productos.txt).")
            if not case.get("expected_behavior_products") and not case.get("expected_behavior"):
                errors.append(f"{prefix} falta expected_behavior_products.")
            if not case.get("client_id"):
                errors.append(f"{prefix} falta client_id (requerido en modo --products-only).")
            tools = case.get("expected_tools_products") or []
            tools_any = case.get("expected_tools_products_any") or []
            if not tools and not tools_any:
                errors.append(f"{prefix} definí expected_tools_products o expected_tools_products_any.")
        else:
            if not case.get("message"):
                errors.append(f"{prefix} mensaje vacío.")
            if not case.get("expected_behavior"):
                errors.append(f"{prefix} falta expected_behavior.")
            tools = case.get("expected_tools") or []
            tools_any = case.get("expected_tools_any") or []
            if not tools and not tools_any:
                errors.append(f"{prefix} definí expected_tools o expected_tools_any.")
        for tool in tools + tools_any:
            if tool not in valid_tools:
                errors.append(f"{prefix} tool inválida '{tool}'.")
        for sku in case.get("expected_skus") or []:
            if sku and sku not in valid_skus:
                errors.append(f"{prefix} SKU '{sku}' no está en catálogo activo.")
    return errors


def apply_products_only_mode(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transforma casos reales para evaluar solo carga de productos (cliente pre-seleccionado)."""
    out: list[dict[str, Any]] = []
    for case in cases:
        if case.get("source") not in {"real", "generated"}:
            continue
        if not case.get("message_products"):
            raise ValueError(
                f"Caso '{case.get('slug')}': sin message_products para modo --products-only."
            )
        nc = dict(case)
        nc["message"] = case["message_products"]
        nc["products_only"] = True
        nc["expected_behavior"] = (
            case.get("expected_behavior_products") or case.get("expected_behavior") or ""
        ).strip()
        nc["expected_tools"] = list(case.get("expected_tools_products") or [])
        nc["expected_tools_any"] = list(
            case.get("expected_tools_products_any")
            or ["load_seller_order_text", "edit_order_for_client"]
        )
        nc["name"] = f"{case['name']} [solo productos]"
        out.append(nc)
    return out


def expand_real_cases_with_llm(
    *,
    schema: str,
    real_cases: list[dict[str, Any]],
    products: list[dict[str, Any]],
    tags: list[dict[str, Any]],
    seller: bool,
    extra_count: int,
    call_openai_chat,
) -> list[dict[str, Any]]:
    if extra_count <= 0:
        return []

    context = load_context(schema)
    manifest = load_manifest(schema)
    profile = "seller" if seller else manifest.get("profile", "client")

    real_txt = json.dumps(
        [{k: c[k] for k in c if k != "fixture_dir"} for c in real_cases],
        ensure_ascii=False,
        indent=2,
    )
    products_txt = json.dumps(products[:40], ensure_ascii=False, indent=2)
    tags_txt = json.dumps(tags[:30], ensure_ascii=False, indent=2)

    system_prompt = f"""Sos un diseñador de pruebas E2E para un agente conversacional B2B ({profile}).
A partir de casos REALES provistos por el distribuidor, generás variantes similares que mantengan la intención de negocio pero cambien redacción, cantidades o productos del catálogo.

Reglas:
- Usá solo SKUs (product_code) del catálogo provisto.
- Cada caso debe tener: name, message, expected_behavior, expected_tools (lista) y opcional expected_tools_any, expected_skus, client_identifier (solo seller).
- Mensajes en español, estilo WhatsApp informal (como reenvíos de vendedores).
- No copies literalmente los casos reales; variá la formulación.
- Perfil activo: {profile}.
"""

    user_prompt = f"""CONTEXTO DE NEGOCIO DEL DISTRIBUIDOR ({schema}):
{context or "(sin contexto.md)"}

CASOS REALES (base):
{real_txt}

CATÁLOGO (muestra):
{products_txt}

TAGS:
{tags_txt}

Generá exactamente {extra_count} casos NUEVOS similares en JSON:
{{"cases": [{{"name": "...", "message": "...", "expected_behavior": "...", "expected_tools": [], "expected_tools_any": [], "expected_skus": [], "client_identifier": null, "tags": []}}]}}
"""

    content = call_openai_chat(system_prompt, user_prompt, json_mode=True)
    payload = json.loads(content)
    generated = payload.get("cases") or payload.get("test_cases") or []
    out: list[dict[str, Any]] = []
    base_id = len(real_cases)
    for i, raw in enumerate(generated[:extra_count], start=1):
        out.append(
            {
                "id": base_id + i,
                "name": raw.get("name") or f"Variante generada {i}",
                "message": (raw.get("message") or "").strip(),
                "expected_skus": list(raw.get("expected_skus") or []),
                "expected_behavior": (raw.get("expected_behavior") or "").strip(),
                "expected_tools": list(raw.get("expected_tools") or []),
                "expected_tools_any": list(raw.get("expected_tools_any") or []),
                "client_identifier": raw.get("client_identifier"),
                "source": "generated",
                "slug": f"generated-{i}",
                "tags": list(raw.get("tags") or []),
                "reference_images": [],
                "sequential_order": base_id + i,
            }
        )
    return out


def resolve_sender_phone(
    case: dict[str, Any],
    manifest: dict[str, Any],
    *,
    default_client_phone: str,
    default_seller_phone: str | None,
    seller_mode: bool,
) -> str:
    if case.get("sender_phone"):
        return str(case["sender_phone"])
    if manifest.get("sender_phone"):
        return str(manifest["sender_phone"])
    if seller_mode and default_seller_phone:
        return default_seller_phone
    return default_client_phone
