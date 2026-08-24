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
WF_ID = "zBDJRgEDeuJuKe62"
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
        existing = None
        by_id = http.get(f"{base}/api/v1/workflows/{WF_ID}", headers=headers)
        if by_id.status_code == 200:
            existing = by_id.json()
        else:
            listed = http.get(f"{base}/api/v1/workflows", params={"limit": 250}, headers=headers)
            listed.raise_for_status()
            listed_data = listed.json()
            rows = listed_data.get("data") if isinstance(listed_data, dict) else listed_data
            for item in rows or []:
                if not isinstance(item, dict):
                    continue
                if item.get("id") == WF_ID or item.get("name") == payload["name"]:
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
        wf_id = data.get("id") or (existing or {}).get("id")
        print("workflow_id", wf_id)
        if wf_id:
            act = http.post(f"{base}/api/v1/workflows/{wf_id}/activate", headers=headers)
            print("activate", act.status_code, act.text[:200])
        print("[INFO] Credential Postgres pooler 6543 debe seguir pegada en ambos nodos.")


if __name__ == "__main__":
    main()
