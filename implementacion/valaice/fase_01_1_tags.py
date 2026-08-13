import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

schema = "valaice"
backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

print(f"[*] Requesting taxonomy proposal from {backend_url}/{schema}/tags/propose-taxonomy...")

try:
    resp = requests.post(f"{backend_url}/{schema}/tags/propose-taxonomy", json={"limit": 300}, timeout=120)
    if resp.status_code == 200:
        data = resp.json()
        print(f"[+] Received taxonomy proposal.")
        os.makedirs(f"implementacion/{schema}/outputs", exist_ok=True)
        with open(f"implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        print(f"[*] Applying taxonomy proposal to Supabase via {backend_url}/{schema}/tags/apply-proposed-taxonomy...")
        apply_resp = requests.post(f"{backend_url}/{schema}/tags/apply-proposed-taxonomy", json=data, timeout=120)
        print(f"Apply response ({apply_resp.status_code}): {apply_resp.text}")
    else:
        print(f"[WARN] Endpoint returned {resp.status_code}: {resp.text}")
except Exception as e:
        print(f"[WARN] Error connecting to backend taxonomy endpoint: {e}")
