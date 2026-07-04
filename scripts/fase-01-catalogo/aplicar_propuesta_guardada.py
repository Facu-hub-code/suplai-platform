import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(
        description="Aplica una propuesta de categorías guardada en JSON a la base de datos vía el backend."
    )
    parser.add_argument("--esquema", required=True, help="El nombre del esquema (tenant) a procesar (ej: al_fuego)")
    parser.add_argument("--backend-url", help="URL base del backend (por defecto lee de BACKEND_URL o usa producción)")

    args = parser.parse_args()

    esquema = args.esquema
    backend_url = args.backend_url or os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app")
    backend_url = backend_url.rstrip("/")

    json_path = f"implementacion/{esquema}/outputs/phase-01-1-propuesta-categorias.json"
    print("=" * 60)
    print(f"APLICANDO PROPUESTA DE CATEGORÍAS GUARDADA PARA: {esquema}")
    print(f"Archivo JSON: {json_path}")
    print(f"Backend URL: {backend_url}")
    print("=" * 60)

    if not os.path.exists(json_path):
        print(f"[FAIL] No se encontró el archivo JSON en: {json_path}")
        sys.exit(1)

    print(f"[*] Cargando propuesta de categorías desde: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    products_list = data.get("products", [])
    print(f"[+] Total de productos cargados: {len(products_list)}")

    # SPEC-060: endpoint de categorías (no tags)
    apply_url = f"{backend_url}/{esquema}/categorias/apply-proposed-taxonomy"
    print(f"[*] Enviando propuesta al backend para impactar Supabase: {apply_url}...")

    try:
        resp = requests.post(apply_url, json={"products": products_list}, timeout=300)
        print("Response status code:", resp.status_code)
        if resp.status_code != 200:
            print(f"[FAIL] Error en categorias/apply-proposed-taxonomy (Código {resp.status_code}): {resp.text}")
            sys.exit(1)

        print("[+] ¡Categorías aplicadas exitosamente en la base de datos de Supabase!")
        print("    RAG de categorías se rebuild en background en el servidor.")

    except Exception as e:
        print(f"[FAIL] Ocurrió un error al interactuar con el backend: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("PROCESO DE APLICACIÓN TERMINADO")
    print("=" * 60)

if __name__ == "__main__":
    main()
