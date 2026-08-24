"""Publica el workflow de shift de fechas demo en n8n (Railway)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
WF_PATH = ROOT / "workflows" / "demo_shift_fechas_pedidos.json"
GEV_ENV = Path("/Users/facundolorenzo/Documents/SuplaiSales/source/test-api-gev/.env")


def main() -> None:
    load_dotenv(GEV_ENV)
    base = (os.getenv("N8N_BASE_URL") or "").rstrip("/")
    key = os.getenv("N8N_API_KEY") or ""
    if not base or not key:
        print("[WARN] N8N_BASE_URL / N8N_API_KEY no configurados. Workflow queda solo en repo.")
        sys.exit(0)
    wf = json.loads(WF_PATH.read_text(encoding="utf-8"))
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {},
    }
    headers = {"X-N8N-API-KEY": key, "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as http:
        listed = http.get(f"{base}/api/v1/workflows", params={"limit": 250}, headers=headers)
        listed.raise_for_status()
        existing = None
        for item in (listed.json().get("data") or listed.json() if isinstance(listed.json(), list) else []):
            if isinstance(item, dict) and item.get("name") == payload["name"]:
                existing = item
                break
        if existing:
            r = http.put(f"{base}/api/v1/workflows/{existing['id']}", headers=headers, json=payload)
            print("update", r.status_code, r.text[:400])
        else:
            r = http.post(f"{base}/api/v1/workflows", headers=headers, json=payload)
            print("create", r.status_code, r.text[:400])
        if r.status_code >= 400:
            sys.exit(1)
        data = r.json()
        print("workflow_id", data.get("id"))
        print("[INFO] Activar en n8n y pegar credential Postgres pooler 6543 (placeholder CONFIGURE_IN_N8N).")


if __name__ == "__main__":
    main()
