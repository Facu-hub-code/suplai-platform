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
        description="Propone y aplica taxonomía de categorías jerárquicas a un tenant usando el backend."
    )
    parser.add_argument("--esquema", required=True, help="El nombre del esquema (tenant) a procesar (ej: al_fuego)")
    parser.add_argument("--limite", type=int, default=300, help="Límite máximo de productos a incluir en la propuesta (default: 300)")
    parser.add_argument("--backend-url", help="URL base del backend (por defecto lee de BACKEND_URL o usa producción)")
    parser.add_argument("--yes", action="store_true", help="Aplica la propuesta automáticamente sin pedir confirmación por consola")

    args = parser.parse_args()

    esquema = args.esquema
    limite = args.limite
    auto_apply = args.yes

    backend_url = args.backend_url or os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app")
    backend_url = backend_url.rstrip("/")

    print("=" * 60)
    print(f"EJECUTANDO PROPUESTA Y APLICACIÓN DE CATEGORÍAS PARA: {esquema}")
    print(f"Backend URL: {backend_url}")
    print(f"Límite de productos: {limite}")
    print("=" * 60)

    # 1. Propose taxonomy via backend (categorias endpoint — SPEC-060)
    propose_url = f"{backend_url}/{esquema}/categorias/propose-taxonomy"
    print(f"[*] Solicitando propuesta de categorías en: {propose_url} (esperando respuesta de IA)...")

    payload = {"limit": limite}

    try:
        resp = requests.post(propose_url, json=payload, timeout=300)
        if resp.status_code != 200:
            print(f"[FAIL] Error en categorias/propose-taxonomy (Código {resp.status_code}): {resp.text}")
            sys.exit(1)

        data = resp.json()
        products_list = data.get("products", [])
        num_products = len(products_list)
        print(f"[+] Se obtuvieron propuestas de categorías para {num_products} productos.")

        # Guardar JSON a la carpeta de outputs local
        output_dir = f"implementacion/{esquema}/outputs"
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/phase-01-1-propuesta-categorias.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[+] Propuesta de categorías guardada localmente en: {output_path}")

        if not products_list:
            print("[WARN] No se encontraron productos para proponer categorías. Finalizando.")
            sys.exit(0)

        # Solicitar confirmación si no se pasó --yes
        if not auto_apply:
            print(f"\n[?] Se han propuesto categorías para {num_products} productos.")
            confirm = input("¿Desea aplicar estas categorías en la base de datos de Supabase? (s/n): ").strip().lower()
            if confirm not in ['s', 'si', 'y', 'yes']:
                print("[*] Aplicación cancelada por el usuario. El archivo JSON fue guardado de todas formas.")
                sys.exit(0)

        # 2. Apply proposed taxonomy via backend (categorias endpoint — SPEC-060)
        apply_url = f"{backend_url}/{esquema}/categorias/apply-proposed-taxonomy"
        print(f"[*] Aplicando categorías en la base de datos vía: {apply_url}...")

        apply_resp = requests.post(apply_url, json={"products": products_list}, timeout=300)
        if apply_resp.status_code != 200:
            print(f"[FAIL] Error en categorias/apply-proposed-taxonomy (Código {apply_resp.status_code}): {apply_resp.text}")
            sys.exit(1)

        print("[+] ¡Categorías aplicadas exitosamente!")
        print("    RAG de categorías se rebuild en background en el servidor.")

    except Exception as e:
        print(f"[FAIL] Ocurrió un error al interactuar con el backend: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("PROCESO DE CATEGORÍAS TERMINADO")
    print("=" * 60)

if __name__ == "__main__":
    main()
