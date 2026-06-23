import os
import sys
import asyncio
import requests
from dotenv import load_dotenv

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Intentar cargar .env
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
dotenv_exists = os.path.exists(dotenv_path)

if dotenv_exists:
    load_dotenv(dotenv_path)
    print("✅ Archivo .env detectado.")
else:
    print("❌ ERROR: No se encontró el archivo .env en la raíz del proyecto.")
    print("👉 Solución: Copia el archivo '.env.example' como '.env' en la raíz y completa las credenciales.")
    print("------------------------------------------------------------")

# 1. Verificar dependencias de Python
print("\n🔍 1. Verificando librerías de Python instaladas...")
libraries = {
    "asyncpg": "Para conectarse a la base de datos de Supabase.",
    "requests": "Para llamar a las APIs de OpenAI, Serper y del Backend.",
    "dotenv": "Para leer el archivo .env."
}

all_libs_ok = True
for lib, desc in libraries.items():
    try:
        if lib == "dotenv":
            import dotenv
        else:
            __import__(lib)
        print(f"  ✅ {lib}: Instalada.")
    except ImportError:
        print(f"  ❌ {lib}: FALTANTE. ({desc})")
        all_libs_ok = False

if not all_libs_ok:
    print("👉 Solución: Ejecuta en la terminal: pip install -r requirements.txt")
    print("------------------------------------------------------------")

# 2. Verificar variables del archivo .env
print("\n🔍 2. Verificando variables de entorno en el .env...")
required_vars = {
    "SUPABASE_DB_URL": "Conexión a la base de datos Postgres de Supabase",
    "OPENAI_API_KEY": "API Key de OpenAI para enriquecimiento y análisis",
    "SEARCH_PROVIDER": "Proveedor de búsqueda en Google (serper o serpapi)"
}

missing_vars = []
for var, desc in required_vars.items():
    val = os.getenv(var)
    if not val:
        missing_vars.append(var)
        print(f"  ❌ {var} (REQUERIDA): Faltante o vacía. ({desc})")
    else:
        if "KEY" in var or "URL" in var:
            masked = val[:15] + "..." if len(val) > 20 else "***"
            print(f"  ✅ {var}: Configurada ({masked})")
        else:
            print(f"  ✅ {var}: Configurada ({val})")

# Verificar variables opcionales
backend_url = os.getenv("BACKEND_URL")
if not backend_url:
    print("  ℹ️ BACKEND_URL (OPCIONAL): No configurada. Se usará la URL por defecto en producción.")
else:
    print(f"  ✅ BACKEND_URL: Configurada ({backend_url})")

# Verificar clave de búsqueda correspondiente al proveedor
search_provider = os.getenv("SEARCH_PROVIDER", "").strip().lower()
if search_provider == "serper":
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        missing_vars.append("SERPER_API_KEY")
        print("  ❌ SERPER_API_KEY: Faltante o vacía. (Requerida porque SEARCH_PROVIDER=serper)")
    else:
        print(f"  ✅ SERPER_API_KEY: Configurada ({serper_key[:10]}...)")
elif search_provider == "serpapi":
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        missing_vars.append("SERPAPI_API_KEY")
        print("  ❌ SERPAPI_API_KEY: Faltante o vacía. (Requerida porque SEARCH_PROVIDER=serpapi)")
    else:
        print(f"  ✅ SERPAPI_API_KEY: Configurada ({serpapi_key[:10]}...)")
elif search_provider:
    print(f"  ❌ SEARCH_PROVIDER: El valor '{search_provider}' no es válido. Debe ser 'serper' o 'serpapi'.")

if missing_vars:
    print("\n👉 Solución: Abre el archivo '.env' y agrega las variables faltantes.")
    print("------------------------------------------------------------")

# 3. Validar conexiones externas (asíncronas)
async def test_connections():
    print("\n🔍 3. Probando conectividad y credenciales...")
    
    # A. Supabase DB URL Connection
    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        try:
            import asyncpg
            conn = await asyncpg.connect(db_url, timeout=10)
            await conn.close()
            print("  ✅ Base de datos (Supabase Postgres): Conexión establecida exitosamente.")
        except Exception as e:
            print(f"  ❌ Base de datos (Supabase Postgres): ERROR DE CONEXIÓN.\n     Detalle: {e}")
            print("     👉 Revisa que el host, puerto, usuario y contraseña en SUPABASE_DB_URL sean correctos y que tengas acceso a internet.")
    else:
        print("  ⚠️ Base de datos (Supabase Postgres): Omitida (Falta la URL en .env).")

    # B. OpenAI API
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {openai_key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                print("  ✅ OpenAI API: Credenciales válidas y conectividad activa.")
            else:
                print(f"  ❌ OpenAI API: ERROR de credenciales (HTTP {resp.status_code}).\n     Respuesta: {resp.text}")
                print("     👉 Revisa que tu OPENAI_API_KEY sea válida, activa y tenga saldo suficiente.")
        except Exception as e:
            print(f"  ❌ OpenAI API: ERROR DE CONEXIÓN.\n     Detalle: {e}")
    else:
        print("  ⚠️ OpenAI API: Omitida (Falta la API Key en .env).")

    # C. Search Provider (Serper / SerpAPI)
    if search_provider == "serper" and os.getenv("SERPER_API_KEY"):
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": os.getenv("SERPER_API_KEY"), "Content-Type": "application/json"}
        payload = {"q": "test query suplai", "gl": "ar", "hl": "es"}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                print("  ✅ Serper API (Búsqueda Google): Conexión y API Key válidas.")
            else:
                print(f"  ❌ Serper API (Búsqueda Google): ERROR (HTTP {resp.status_code}).\n     Respuesta: {resp.text}")
                print("     👉 Revisa que tu SERPER_API_KEY sea válida y activa.")
        except Exception as e:
            print(f"  ❌ Serper API (Búsqueda Google): ERROR DE CONEXIÓN.\n     Detalle: {e}")
    elif search_provider == "serpapi" and os.getenv("SERPAPI_API_KEY"):
        url = "https://serpapi.com/search"
        params = {"q": "test query suplai", "api_key": os.getenv("SERPAPI_API_KEY")}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                print("  ✅ SerpAPI (Búsqueda Google): Conexión y API Key válidas.")
            else:
                print(f"  ❌ SerpAPI (Búsqueda Google): ERROR (HTTP {resp.status_code}).\n     Respuesta: {resp.text}")
                print("     👉 Revisa que tu SERPAPI_API_KEY sea válida y activa.")
        except Exception as e:
            print(f"  ❌ SerpAPI (Búsqueda Google): ERROR DE CONEXIÓN.\n     Detalle: {e}")
    else:
        print("  ⚠️ Búsqueda Google: Omitida (Sin proveedor o clave configurada).")

    # D. Backend URL
    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    try:
        # Intentamos consultar el health del backend o docs
        resp = requests.get(f"{backend_url}/docs", timeout=10)
        if resp.status_code == 200:
            print(f"  ✅ Backend ({backend_url}): Conectividad establecida y Swagger disponible.")
        else:
            resp_root = requests.get(backend_url, timeout=10)
            if resp_root.status_code < 500:
                print(f"  ✅ Backend ({backend_url}): Conectividad establecida (HTTP {resp_root.status_code}).")
            else:
                print(f"  ❌ Backend ({backend_url}): El servidor respondió con un error del servidor (HTTP {resp_root.status_code}).")
    except Exception as e:
        print(f"  ❌ Backend ({backend_url}): ERROR DE CONEXIÓN.\n     Detalle: {e}")
        print("     👉 Revisa si el backend está activo o si la URL es correcta.")

if all_libs_ok:
    asyncio.run(test_connections())
else:
    print("\n⚠️ Omitiendo validación de conexiones porque faltan dependencias básicas de Python.")

print("\n============================================================")
print("FIN DEL DIAGNÓSTICO DE ENTORNO")
print("============================================================")
