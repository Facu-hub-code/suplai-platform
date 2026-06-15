"""
Carga de journeys E2E multi-paso (carga → edición → consulta) por caso de uso real.

Estructura:
  implementacion/{schema}/journeys/
    manifest.json
    {slug}/
      journey.json
      pasos/
        01-carga-inicial.txt
        02-editar-*.txt
        02-editar-*-aislado.txt  (opcional, mensaje autocontenido para modo isolated)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
IMPLEMENTACION = ROOT / "implementacion"


def journeys_root(schema: str) -> Path:
    return IMPLEMENTACION / schema / "journeys"


def load_journey_manifest(schema: str) -> dict[str, Any]:
    path = journeys_root(schema) / "manifest.json"
    if not path.is_file():
        return {"schema": schema, "profile": "seller"}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {"schema": schema}


def _read_step_message(pasos_dir: Path, step: dict[str, Any], *, isolated: bool) -> str:
    if isolated:
        for key in ("isolated_message_file", "message_aislado_file"):
            fname = step.get(key)
            if fname:
                p = pasos_dir / fname
                if p.is_file():
                    return p.read_text(encoding="utf-8").strip()
    if step.get("message"):
        return str(step["message"]).strip()
    fname = step.get("message_file")
    if fname:
        p = pasos_dir / fname
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    raise ValueError(f"Paso sin mensaje en {pasos_dir}: {step.get('name')}")


def list_journey_dirs(schema: str) -> list[Path]:
    root = journeys_root(schema)
    if not root.is_dir():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "journey.json").is_file()],
        key=lambda p: p.name,
    )


def load_journeys(schema: str, *, isolated: bool = False) -> list[dict[str, Any]]:
    dirs = list_journey_dirs(schema)
    if not dirs:
        raise FileNotFoundError(
            f"No hay journeys en {journeys_root(schema)}/*/journey.json"
        )

    journeys: list[dict[str, Any]] = []
    for jdir in dirs:
        with (jdir / "journey.json").open(encoding="utf-8") as f:
            spec = json.load(f)
        pasos_dir = jdir / "pasos"
        steps_raw = spec.get("steps") or []
        steps: list[dict[str, Any]] = []
        for i, st in enumerate(steps_raw, start=1):
            msg = _read_step_message(pasos_dir, st, isolated=isolated)
            steps.append(
                {
                    "step_order": st.get("step_order", i),
                    "name": st.get("name") or f"Paso {i}",
                    "message": msg,
                    "expected_skus": list(st.get("expected_skus") or []),
                    "expected_behavior": (st.get("expected_behavior") or "").strip(),
                    "expected_tools": list(st.get("expected_tools") or []),
                    "expected_tools_any": list(st.get("expected_tools_any") or []),
                    "tags": list(st.get("tags") or []),
                }
            )
        steps.sort(key=lambda s: s["step_order"])
        journeys.append(
            {
                "slug": spec.get("slug") or jdir.name,
                "name": spec.get("name") or jdir.name,
                "order": spec.get("order", 0),
                "client_identifier": spec.get("client_identifier"),
                "source_case": spec.get("source_case"),
                "steps": steps,
                "fixture_dir": str(jdir.relative_to(ROOT)),
            }
        )

    journeys.sort(key=lambda j: (j.get("order", 0), j["slug"]))
    return journeys


def flatten_journey_steps(
    journeys: list[dict[str, Any]],
    *,
    journey_mode: str,
) -> list[dict[str, Any]]:
    """
    Convierte journeys en casos ejecutables para el runner.
    journey_mode: chained | isolated
    """
    cases: list[dict[str, Any]] = []
    case_id = 0
    for journey in journeys:
        for step in journey["steps"]:
            case_id += 1
            cases.append(
                {
                    "id": case_id,
                    "name": f"[Journey] {journey['name']} — {step['name']}",
                    "message": step["message"],
                    "expected_skus": step.get("expected_skus") or [],
                    "expected_behavior": step.get("expected_behavior") or "",
                    "expected_tools": step.get("expected_tools") or [],
                    "expected_tools_any": step.get("expected_tools_any") or [],
                    "client_identifier": journey.get("client_identifier"),
                    "source": "journey",
                    "slug": f"{journey['slug']}/paso-{step['step_order']}",
                    "tags": list(step.get("tags") or []),
                    "fixture_dir": journey.get("fixture_dir"),
                    "journey_slug": journey["slug"],
                    "journey_name": journey["name"],
                    "journey_step": step["step_order"],
                    "journey_total_steps": len(journey["steps"]),
                    "journey_mode": journey_mode,
                    "journey_is_first_step": step["step_order"] == 1,
                    "journey_is_last_step": step["step_order"] == len(journey["steps"]),
                }
            )
    return cases


def validate_journey_cases(
    cases: list[dict[str, Any]],
    valid_skus: set[str],
    valid_tools: set[str],
) -> list[str]:
    errors: list[str] = []
    for case in cases:
        prefix = f"Journey [{case.get('slug', case.get('id'))}]:"
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
