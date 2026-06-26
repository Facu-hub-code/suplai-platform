"""
preparar_red_comercial.py
=========================
Genera los 3 CSVs de red comercial mock para un tenant Suplai Sales,
siguiendo las especificaciones de phase-04-red-comercial/SKILL.md:

  - phase-04-vendedores.csv   (3 vendedores mock)
  - phase-04-zonas.csv        (6 zonas independientes con geometría PostGIS MultiPolygon)
  - phase-04-clientes.csv     (50 clientes geolocalizados, ~8-9 por zona)

Especificaciones de la skill:
  - Vendedores: nombres locales AR, tel. prefijo 549, email @suplaisales.mock, is_mock=true
  - Zonas: barrios/rutas REALES de ciudad_base; polígonos CHICOS e independientes;
           zone_type solo 'sales' o 'route'; SRID=4326;MULTIPOLYGON; dia_visita rotado lu-sá
  - Clientes: dispersión 0.01-0.08 grados desde centro de zona; nombres acorde al rubro;
              lista_precios_id 1-4 distribuido equitativamente; teléfonos únicos.

Configuración personalizable por tenant:
  - "red_comercial": clave opcional en config.json para proveer datos personalizados:
      {
        "coordenadas_centro": [-31.3547, -64.2442],   // Sobrescribe manifest.coordenadas_centro
        "vendedores": [...],
        "zonas": [...],
        "nombres_comerciales": [...]
      }
  - Si config.json no tiene "red_comercial" (o le faltan claves), el script usa OpenAI
    para generar datos contextuales a partir de ciudad_base y rubro del manifest.

Campos OBLIGATORIOS en manifest.yaml (a partir de esta fase):
  - ciudad_base:         "Ciudad, Provincia, Argentina"
  - rubro:               "carnicería / parrilla"  (texto libre, describe el negocio)
  - coordenadas_centro:  [-31.3547, -64.2442]     (lat, lon del centro de operaciones)

Uso:
    python scripts/preparar_red_comercial.py --esquema <nombre_esquema>

Variables de entorno opcionales (en .env):
    OPENAI_API_KEY
    OPENAI_BASE_URL   (default: https://api.openai.com/v1)
    OPENAI_MODEL      (default: gpt-4o-mini)
"""

import os
import sys
import csv
import json
import yaml
import math
import random
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

DIAS_VISITA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]
DIAS_ENTREGA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]

# Mapa de normalización para valores con tilde que puede devolver OpenAI
DIA_NORMALIZE = {
    "sábado": "sabado",
    "miércoles": "miercoles",
    "miércoles": "miercoles",  # por si viene con acento diferente
}


def normalize_dia(dia: str) -> str:
    """Normaliza el nombre de un día quitando tildes y pasando a minúsculas."""
    if not dia:
        return "lunes"
    d = dia.lower().strip()
    # Mapa explícito de variantes con tilde
    d = DIA_NORMALIZE.get(d, d)
    # Verificar que sea válido; si no, usar lunes como fallback
    if d not in DIAS_VISITA:
        print(f"  [WARN] Dia de visita desconocido: '{dia}' → usando 'lunes' como fallback.")
        return "lunes"
    return d


# ---------------------------------------------------------------------------
# Helpers geométricos
# ---------------------------------------------------------------------------

def build_multipolygon_wkt(coords: list) -> str:
    """Construye un WKT SRID=4326;MULTIPOLYGON a partir de lista de [lon, lat]."""
    coords_str = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return f"SRID=4326;MULTIPOLYGON((({coords_str})))"


def cuadrado_polygon(lon_center: float, lat_center: float, delta: float = 0.004) -> list:
    """Genera 5 vértices de un cuadrado cerrado alrededor de (lon_center, lat_center)."""
    return [
        (lon_center - delta, lat_center - delta),
        (lon_center + delta, lat_center - delta),
        (lon_center + delta, lat_center + delta),
        (lon_center - delta, lat_center + delta),
        (lon_center - delta, lat_center - delta),  # cerrar polígono
    ]

def obtener_coordenadas_ciudad(ciudad: str) -> tuple:
    """Obtiene el centroide geométrico de una ciudad consultando Nominatim (OpenStreetMap)."""
    try:
        headers = {"User-Agent": "SuplaiSales-MockGen/1.0"}
        url = f"https://nominatim.openstreetmap.org/search?q={ciudad}&format=json&limit=1"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            return float(data["lat"]), float(data["lon"])
    except Exception as e:
        print(f"[WARN] No se pudo obtener coordenadas de Nominatim para {ciudad}: {e}")
    return None, None


def obtener_centro_zona_grid(lat_centro: float, lon_centro: float, zona_idx: int):
    """
    Distribuye hasta 6 zonas en una grilla 3x2 alrededor del centro de la ciudad para evitar superposición.
    W = 0.02 grados, H = 0.02 grados.
    """
    W = 0.02
    H = 0.02
    col = (zona_idx % 3) - 1   # -1, 0, 1
    row = 0.5 if zona_idx < 3 else -0.5
    
    lat_c = lat_centro + row * H
    lon_c = lon_centro + col * W
    return round(lat_c, 5), round(lon_c, 5)

def dispersar_coordenada(lat_base: float, lon_base: float, zona_idx: int, cliente_idx: int):
    """
    Genera lat/lon estrictamente dentro de la celda de la zona para evitar solapamientos.
    Celda es W=0.02, H=0.02 (extensión +/- 0.01 desde el centro).
    Dispersamos a los clientes en un radio interno de +/- 0.005 para hacer zonas más compactas.
    """
    random.seed(zona_idx * 100 + cliente_idx + 999)
    delta_lat = random.uniform(-0.005, 0.005)
    delta_lon = random.uniform(-0.005, 0.005)
    return round(lat_base + delta_lat, 6), round(lon_base + delta_lon, 6)


def generar_telefono(seed: int, prefijo_pais: str = "549") -> str:
    """Genera teléfono único con seed determinista."""
    random.seed(seed + 7777)
    if prefijo_pais == "549":
        codigo_area = random.choice(["351", "387", "341", "261", "299", "381", "358"])
        sufijo = random.randint(1000000, 9999999)
        return f"{prefijo_pais}{codigo_area}{sufijo}"
    else:
        digitos = random.randint(10000000, 999999999)
        return f"{prefijo_pais}{digitos}"


# ---------------------------------------------------------------------------
# Generación por OpenAI
# ---------------------------------------------------------------------------

def generar_red_con_ia(ciudad_base: str, rubro: str, lat: float, lon: float, prefijo_pais: str = "549") -> dict:
    """
    Llama a OpenAI para generar datos contextuales de red comercial.
    Sigue las especificaciones de phase-04-red-comercial/SKILL.md:
    - Zonas con nombres de BARRIOS REALES de ciudad_base
    - zone_type solo 'sales' o 'route'
    - Polígonos pequeños (barrios puntuales, no coberturas de ciudad entera)
    - Clientes con nombres acorde al rubro
    """
    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY no configurada. Se usará generación geométrica por defecto.")
        return {}

    prompt_sistema = (
        "Sos un experto en implementaciones comerciales para distribuidoras en Argentina. "
        "Generás datos mock realistas de red comercial. "
        "IMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido, sin explicaciones ni bloques de código markdown."
    )

    prompt_usuario = f"""
Genera una red comercial mock para una distribuidora argentina:

- Ciudad base: {ciudad_base}
- Rubro: {rubro}
- Coordenadas centro: lat={lat}, lon={lon}

Devuelve un JSON con EXACTAMENTE esta estructura:

{{
  "vendedores": [
    {{
      "nombre": "Nombre Apellido",
      "telefono": "{prefijo_pais}XXXXXXXXX",
      "email": "nombre.apellido@suplaisales.mock",
      "zona": "NORTE",
      "codigo_ruta": "R01"
    }}
  ],
  "zonas": [
    {{
      "nombre": "ZONA NOROESTE - Nombre Barrio Real",
      "dia_visita": "lunes",
      "color": "#E74C3C",
      "codigo_ruta": "R01-A",
      "zone_type": "sales",
      "description": "Zona comercial barrio X, acceso por Av. Y.",
      "vendedor_idx": 0
    }}
  ],
  "nombres_comerciales": [
    "Nombre Comercial 1"
  ]
}}

Requisitos OBLIGATORIOS:
1. Exactamente 3 vendedores con nombres argentinos reales (no inventados).
   Teléfono: El número debe comenzar con {prefijo_pais} seguido de los dígitos locales correspondientes, respetando la longitud de un número celular de {ciudad_base}. NO incluyas signos `+` ni guiones.
2. Exactamente 6 zonas en estas direcciones específicas: Noroeste, Norte, Noreste, Suroeste, Sur, Sureste.
   - El atributo "nombre" debe tener el formato "ZONA <DIRECCION> - Nombre Barrio Real".
   - NO incluyas coordenadas geográficas.
   - zone_type SOLO puede ser 'sales' o 'route'. NO usar otros valores.
   - dia_visita SOLO puede ser: lunes, martes, miercoles, jueves, viernes, sabado.
   - Los nombres de zonas DEBEN usar barrios o localidades REALES de {ciudad_base}
     (ej. Villa Allende, Mendiolaza, Malagueño, Valle Escondido, Argüello, La Calera).
   - Cada zona en un barrio DISTINTO y pequeño (puntual), NO una zona que cubra toda la ciudad.
3. Al menos 55 nombres comerciales acordes al rubro '{rubro}'.
   Para carnicería/parrilla: usar Parrilla, Asadería, Carnicería, Restaurante, Almacén + apodo local.
   Para pinturería: usar Pinturería, Ferretería, Corralón + apodo local.
   Los nombres deben ser variados y realistas para Argentina.
4. Colores hex brillantes y de alto contraste para las zonas (no blancos ni grises).
"""

    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": prompt_usuario},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            # Validar zone_type: SKILL.md solo permite 'sales' o 'route'
            ZONE_TYPES_VALIDOS = {"sales", "route"}
            for z in data.get("zonas", []):
                if z.get("zone_type") not in ZONE_TYPES_VALIDOS:
                    print(f"  [WARN] zone_type inválido '{z.get('zone_type')}' corregido a 'sales'.")
                    z["zone_type"] = "sales"
            return data
        else:
            print(f"[WARN] Error OpenAI HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[WARN] Error llamando a OpenAI: {e}")

    return {}


def fallback_geometrico(lat: float, lon: float, rubro: str, prefijo_pais: str = "549") -> dict:
    """
    Genera 3 vendedores y 6 zonas con polígonos distribuidos angularmente.
    zone_type siempre 'sales' o 'route' según SKILL.md.
    Nombres de comercios adaptados al rubro detectado.
    """
    print("[*] Usando generación geométrica de fallback (sin OpenAI)...")

    vendedores = [
        {
            "nombre": "Martín Herrera",
            "telefono": generar_telefono(1, prefijo_pais),
            "email": "martin.herrera@suplaisales.mock",
            "zona": "NORTE",
            "codigo_ruta": "R01",
        },
        {
            "nombre": "Valeria Díaz",
            "telefono": generar_telefono(2, prefijo_pais),
            "email": "valeria.diaz@suplaisales.mock",
            "zona": "SUR",
            "codigo_ruta": "R02",
        },
        {
            "nombre": "Pablo Romero",
            "telefono": generar_telefono(3, prefijo_pais),
            "email": "pablo.romero@suplaisales.mock",
            "zona": "CENTRO-ESTE",
            "codigo_ruta": "R03",
        },
    ]

    colores = ["#E74C3C", "#E67E22", "#27AE60", "#2980B9", "#8E44AD", "#F39C12"]
    # Alternar entre 'sales' y 'route' como permite la skill
    zone_types = ["sales", "route", "sales", "route", "sales", "route"]
    sectores = ["Norte", "Noroeste", "Sur", "Suroeste", "Centro", "Este"]

    zonas = []
    for i in range(6):
        angulo = math.radians(i * 60)
        dist = 0.016  # ~1.8 km de desplazamiento del centro
        lon_c = round(lon + dist * math.cos(angulo), 4)
        lat_c = round(lat + dist * math.sin(angulo), 4)
        zonas.append({
            "nombre": f"ZONA {sectores[i].upper()} - Sector {i+1}",
            "dia_visita": DIAS_VISITA[i],
            "color": colores[i],
            "codigo_ruta": f"R0{(i//2)+1}-{'A' if i%2==0 else 'B'}",
            "zone_type": zone_types[i],
            "description": f"Zona comercial sector {sectores[i].lower()} de la ciudad base.",
            "vendedor_idx": i // 2,
            "lon_center": lon_c,
            "lat_center": lat_c,
        })

    # Nombres de comercios adaptados al rubro — según SKILL.md:
    # "ferreterías/pinturerías/corralones si rubro pintura; acorde al rubro del tenant"
    rubro_lower = rubro.lower()
    if any(k in rubro_lower for k in ["carnicería", "carniceria", "parrilla", "carne"]):
        terminos = ["Parrilla", "Asadería", "Carnicería", "Restaurante", "Rotisería", "Almacén"]
    elif any(k in rubro_lower for k in ["pinturería", "pintureria", "pintura"]):
        terminos = ["Pinturería", "Corralón", "Ferretería", "Pinturas", "Materiales", "Constructor"]
    elif any(k in rubro_lower for k in ["ferretería", "ferreteria"]):
        terminos = ["Ferretería", "Herramientas", "Corralón", "Materiales", "Constructor", "Taller"]
    elif any(k in rubro_lower for k in ["farmacia"]):
        terminos = ["Farmacia", "Droguería", "Botica", "Salud", "Medicamentos", "Dispensario"]
    else:
        terminos = ["Almacén", "Minimercado", "Comercio", "Distribuidora", "Mercadito", "Tienda"]

    apodos = [
        "El Rincón", "Don Santos", "Los Andes", "La Pampa", "El Gaucho",
        "La Esquina", "San Martín", "El Familiar", "Las Brasas", "Río Grande",
        "Central", "El Asador", "El Fogón", "Los Pinos", "El Quebracho",
        "La Criolla", "Don Pedro", "El Manantial", "El Matrero", "La Tradición",
        "El Pionero", "El Corral", "El Rancho", "Las Achuras", "El Molino",
        "El Pueblo", "El Portal", "La Querencia", "El Recreo", "La Leña",
        "El Patio", "El Mirador", "El Rodeo", "La Estancia", "El Campo",
        "Las Sierras", "El Algarrobo", "La Chacra", "Don Rafael", "El Cortijo",
        "Don Mario", "La Cañada", "El Cruce", "Don Juan", "El Encuentro",
        "La Unión", "El Nativo", "Don Carlos", "La Cumbre", "Las Flores",
        "El Sauce", "El Paraíso", "El Nogal", "Don Roberto", "La Arboleda",
    ]

    nombres_comerciales = []
    for i, apodo in enumerate(apodos):
        termino = terminos[i % len(terminos)]
        nombres_comerciales.append(f"{termino} {apodo}")

    return {
        "vendedores": vendedores,
        "zonas": zonas,
        "nombres_comerciales": nombres_comerciales,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Genera los CSVs de red comercial mock para un tenant Suplai Sales."
    )
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    esquema = args.esquema

    # 1. Leer manifest
    manifest_path = f"implementacion/{esquema}/manifest.yaml"
    if not os.path.exists(manifest_path):
        print(f"[FAIL] No se encontró el manifest en: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = yaml.safe_load(mf)

    ciudad_base = manifest.get("ciudad_base", "Córdoba, Argentina")
    rubro = manifest.get("rubro", "")
    if not rubro:
        print("[WARN] El campo 'rubro' no está definido en manifest.yaml.")
        print("       Agregá 'rubro: <descripción>' al manifest para mejor contextualización.")
        print("       Usando 'distribuidora de alimentos' como valor por defecto.")
        rubro = "distribuidora de alimentos"

    # Coordenadas del centro (lat, lon) — campo estándar del manifest
    coords_manifest = manifest.get("coordenadas_centro", None)

    print(f"[*] Esquema:      {esquema}")
    print(f"[*] Ciudad base:  {ciudad_base}")
    print(f"[*] Rubro:        {rubro}")

    # 2. Leer config.json del tenant (si existe)
    config_path = f"implementacion/{esquema}/config.json"
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as cf:
            config = json.load(cf)

    red_config = config.get("red_comercial", {})

    prefijo_pais = manifest.get("prefijo_pais")
    if not prefijo_pais:
        cb_lower = ciudad_base.lower()
        if "chile" in cb_lower:
            prefijo_pais = "569"
        elif "méxico" in cb_lower or "mexico" in cb_lower:
            prefijo_pais = "52"
        elif "colombia" in cb_lower:
            prefijo_pais = "57"
        elif "perú" in cb_lower or "peru" in cb_lower:
            prefijo_pais = "51"
        elif "uruguay" in cb_lower:
            prefijo_pais = "598"
        else:
            prefijo_pais = "549"


    # 3. Determinar coordenadas centro (Prioridad: config.json > Nominatim > manifest > fallback)
    coords_config = red_config.get("coordenadas_centro", None)
    if coords_config:
        lat_centro = float(coords_config[0])
        lon_centro = float(coords_config[1])
        print(f"[*] Coordenadas (config.json):     {lat_centro}, {lon_centro}")
    else:
        print(f"[*] Buscando centro geográfico de '{ciudad_base}' en OpenStreetMap...")
        lat_nom, lon_nom = obtener_coordenadas_ciudad(ciudad_base)
        if lat_nom and lon_nom:
            lat_centro = lat_nom
            lon_centro = lon_nom
            print(f"[*] Coordenadas (OpenStreetMap): {lat_centro}, {lon_centro}")
        elif coords_manifest:
            lat_centro = float(coords_manifest[0])
            lon_centro = float(coords_manifest[1])
            print(f"[*] Coordenadas (manifest.yaml fallback): {lat_centro}, {lon_centro}")
        else:
            # Último fallback: centroide de Córdoba Capital
            lat_centro = -31.4135
            lon_centro = -64.1810
            print(f"[WARN] Usando centroide Córdoba Capital por defecto: {lat_centro}, {lon_centro}")

    # 4. Resolver datos: config.json tiene prioridad → luego OpenAI → luego fallback geométrico
    vendedores_data = red_config.get("vendedores", None)
    zonas_data = red_config.get("zonas", None)
    nombres_comerciales = red_config.get("nombres_comerciales", None)

    if vendedores_data and zonas_data and nombres_comerciales:
        print("[*] Usando datos de red_comercial desde config.json.")
    else:
        print("[*] Datos de red_comercial no encontrados en config.json. Generando con IA...")
        ia_data = generar_red_con_ia(ciudad_base, rubro, lat_centro, lon_centro, prefijo_pais)

        if ia_data.get("vendedores") and ia_data.get("zonas") and ia_data.get("nombres_comerciales"):
            print("[*] Datos generados con éxito por OpenAI.")
            vendedores_data = ia_data["vendedores"]
            zonas_data = ia_data["zonas"]
            nombres_comerciales = ia_data["nombres_comerciales"]
        else:
            datos_fb = fallback_geometrico(lat_centro, lon_centro, rubro)
            vendedores_data = datos_fb["vendedores"]
            zonas_data = datos_fb["zonas"]
            nombres_comerciales = datos_fb["nombres_comerciales"]

    # Validar conteos mínimos
    if len(vendedores_data) < 3:
        print(f"[WARN] Se esperaban 3 vendedores, se obtuvieron {len(vendedores_data)}. Completando con fallback.")
        fb = fallback_geometrico(lat_centro, lon_centro, rubro)
        vendedores_data = (vendedores_data + fb["vendedores"])[:3]

    if len(zonas_data) < 6:
        print(f"[WARN] Se esperaban 6 zonas, se obtuvieron {len(zonas_data)}. Completando con fallback.")
        fb = fallback_geometrico(lat_centro, lon_centro, rubro)
        zonas_data = (zonas_data + fb["zonas"])[:6]

    # Asegurar al menos 55 nombres comerciales
    while len(nombres_comerciales) < 55:
        nombres_comerciales.append(f"Comercio Nro. {len(nombres_comerciales) + 1}")

    # 5. Escribir CSVs
    output_dir = f"implementacion/{esquema}/outputs"
    os.makedirs(output_dir, exist_ok=True)

    # --- Vendedores ---
    vendedores_path = f"{output_dir}/phase-04-vendedores.csv"
    with open(vendedores_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["nombre", "telefono", "email", "zona", "codigo_ruta", "is_mock"]
        )
        writer.writeheader()
        for v in vendedores_data[:3]:
            writer.writerow({
            "nombre": v["nombre"],
                "telefono": v["telefono"],
                "email": v["email"],
                "zona": v.get("zona", "GENERAL"),
                "codigo_ruta": v.get("codigo_ruta", "R00"),
                "is_mock": "true",
            })
    print(f"✅ Vendedores: {len(vendedores_data[:3])} → {vendedores_path}")

    # --- Generación de Clientes en Memoria y Agrupación por Zona ---
    clientes_por_zona = 50 // min(len(zonas_data), 6)
    resto = 50 % min(len(zonas_data), 6)

    clientes_rows = []
    cliente_num = 1
    nombre_idx = 0
    coords_por_zona = {i: [] for i in range(6)}

    for zona_idx, zona in enumerate(zonas_data[:6]):
        count = clientes_por_zona + (1 if zona_idx < resto else 0)
        vendedor_idx = int(zona.get("vendedor_idx", zona_idx // 2))
        vendedor = vendedores_data[min(vendedor_idx, len(vendedores_data) - 1)]
        dia_visita = normalize_dia(zona.get("dia_visita", DIAS_VISITA[zona_idx % len(DIAS_VISITA)]))

        # Forzar el uso del centro geográfico de la grilla para evitar superposición
        lat_zona, lon_zona = obtener_centro_zona_grid(lat_centro, lon_centro, zona_idx)
        # Actualizamos la zona para que el bounding box use el centro correcto si no hay clientes (fallback)
        zona["lat_center"] = lat_zona
        zona["lon_center"] = lon_zona

        for c in range(count):
            lat, lng = dispersar_coordenada(lat_zona, lon_zona, zona_idx, c)
            coords_por_zona[zona_idx].append((lng, lat)) # (lon, lat)

            razon_social = nombres_comerciales[nombre_idx % len(nombres_comerciales)]
            nombre_idx += 1
            lista_precios_id = (cliente_num % 4) + 1
            dia_entrega_idx = (DIAS_ENTREGA.index(dia_visita) + 1) % len(DIAS_ENTREGA)
            dia_entrega = DIAS_ENTREGA[dia_entrega_idx]

            clientes_rows.append({
                "numero": cliente_num,
                "razon_social": razon_social,
                "nombre_contacto": razon_social,
                "phone_number": generar_telefono(cliente_num + 5000, prefijo_pais),
                "lista_precios_id": lista_precios_id,
                "codigo": cliente_num,
                "dia_de_visita": dia_visita,
                "dia_de_entrega": dia_entrega,
                "direccion": f"Zona {zona['nombre']} - {ciudad_base}",
                "vendedor_nombre": vendedor["nombre"],
                "vendedor_idx": vendedor_idx,
                "zona_idx": zona_idx,
                "lat": lat,
                "lng": lng,
                "is_mock": "true",
            })
            cliente_num += 1

    # --- Zonas ---
    # SKILL.md: zone_type solo 'sales' o 'route'; polígonos CHICOS (barrios puntuales)
    ZONE_TYPES_VALIDOS = {"sales", "route"}
    zonas_path = f"{output_dir}/phase-04-zonas.csv"
    with open(zonas_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "nombre", "zone_type", "description", "color",
            "dia_visita", "codigo_ruta", "vendedor_idx", "geometry_wkt", "is_mock",
        ])
        writer.writeheader()
        for zona_idx, z in enumerate(zonas_data[:6]):
            # Construir geometría a partir del bounding box de sus clientes si hay coordenadas disponibles
            if coords_por_zona[zona_idx]:
                lons = [pt[0] for pt in coords_por_zona[zona_idx]]
                lats = [pt[1] for pt in coords_por_zona[zona_idx]]
                min_lon, max_lon = min(lons), max(lons)
                min_lat, max_lat = min(lats), max(lats)
                
                # Agregar margen (padding) de 0.0008 (~90 metros) para contener a los clientes
                padding = 0.0008
                poly = [
                    (min_lon - padding, min_lat - padding),
                    (max_lon + padding, min_lat - padding),
                    (max_lon + padding, max_lat + padding),
                    (min_lon - padding, max_lat + padding),
                    (min_lon - padding, min_lat - padding),
                ]
                geom = build_multipolygon_wkt(poly)
            elif "coords" in z:
                coords = z["coords"]
                if coords[0] != coords[-1]:
                    coords = coords + [coords[0]]
                geom = build_multipolygon_wkt(coords)
            elif "lon_center" in z and "lat_center" in z:
                poly = cuadrado_polygon(float(z["lon_center"]), float(z["lat_center"]), delta=0.004)
                geom = build_multipolygon_wkt(poly)
            else:
                poly = cuadrado_polygon(lon_centro, lat_centro, delta=0.004)
                geom = build_multipolygon_wkt(poly)

            # Forzar zone_type válido según SKILL.md
            zt = z.get("zone_type", "sales")
            if zt not in ZONE_TYPES_VALIDOS:
                print(f"  [WARN] zone_type '{zt}' no permitido → corrigiendo a 'sales'.")
                zt = "sales"

            writer.writerow({
                "nombre": z["nombre"],
                "zone_type": zt,
                "description": z.get("description", ""),
                "color": z.get("color", "#3498DB"),
                "dia_visita": normalize_dia(z.get("dia_visita", DIAS_VISITA[int(z.get("vendedor_idx", 0)) % 6])),
                "codigo_ruta": z.get("codigo_ruta", "R00-A"),
                "vendedor_idx": int(z.get("vendedor_idx", 0)),
                "geometry_wkt": geom,
                "is_mock": "true",
            })
    print(f"✅ Zonas: {len(zonas_data[:6])} → {zonas_path}")

    # --- Escribir Clientes ---
    clientes_path = f"{output_dir}/phase-04-clientes.csv"
    with open(clientes_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "numero", "razon_social", "nombre_contacto", "phone_number",
            "lista_precios_id", "codigo", "dia_de_visita", "dia_de_entrega",
            "direccion", "vendedor_nombre", "vendedor_idx", "zona_idx", "lat", "lng", "is_mock",
        ])
        writer.writeheader()
        for crow in clientes_rows:
            writer.writerow(crow)
    print(f"✅ Clientes: {cliente_num - 1} → {clientes_path}")

    # Preview
    print("\n--- VENDEDORES ---")
    for v in vendedores_data[:3]:
        print(f"  {v['nombre']} | {v['telefono']} | zona: {v.get('zona', '')}")

    print("\n--- ZONAS ---")
    for z in zonas_data[:6]:
        print(f"  {z['nombre']} | dia: {z.get('dia_visita', '?')} | vendedor_idx: {z.get('vendedor_idx', 0)}")

    print(f"\n✅ Generación completa para esquema '{esquema}'. Outputs en: {output_dir}")
    print("\nPara personalizar, agregá la clave 'red_comercial' en config.json del tenant.")


if __name__ == "__main__":
    main()
