# Dimer McCain Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-14-dimer-recuperacion-mccain-design.md`

**Goal:** Configurar una campaña puntual para recuperar 30 clientes perdidos de papas McCain con personalización por nombre y reconocimiento de consultas por corte 7/10/12 mm y “kilo con IVA”.

**Architecture:** Un script determinista genera previews CSV y actualiza el JSON local del prompt sin escribir en BD. La aplicación productiva se realiza después mediante una única transacción Supabase acotada a `dimer`, seguida por una consulta consolidada de verificación.

**Tech Stack:** Python estándar para artefactos, PostgreSQL/Supabase MCP para datos, configuración JSON de implementación y agenda Motor A.

## Global Constraints

- Schema único: `dimer`; proyecto Supabase `cvlbietibaaehgeimxgw`.
- No modificar precios, plantilla Meta ni otros tenants.
- Base de datos vía MCP Supabase; no usar conexión directa `5432`.
- Antes de escribir, repetir textualmente `dimer` y confirmar el alcance.
- Los CSV de preview deben existir y tener conteos exactos antes del apply.
- “Precio por kilo” y “kilo con IVA” se responden con el precio final de la unidad mínima de venta y su formato; no se calcula un valor por 1 kg ni se convierten kilos solicitados a bolsas.
- Los 14 productos mantienen `es_pesable=false`; `peso_referencia_kg` describe el peso de una bolsa y `unidades_por_bulto` la cantidad de bolsas de la caja.
- La agenda se guarda a `11:00` del reloj operacional del backend para entregar a las `10:00` de Chile el 2026-08-17.
- No cambiar `AGENDA_TZ`: es global y afectaría otros tenants.
- Commits solo si el usuario los pide.

## File map

| Path | Responsabilidad |
|---|---|
| `scripts/dimer/preparar_recuperacion_mccain.py` | Fuente determinista de clientes, alias, pesos y bloque de prompt; genera previews |
| `implementacion/dimer/outputs/recuperacion-mccain-clientes.csv` | 30 clientes y nombres de pila aprobados |
| `implementacion/dimer/outputs/recuperacion-mccain-aliases.csv` | Alias nuevos por SKU y peso |
| `implementacion/dimer/outputs/recuperacion-mccain-pesos.csv` | Peso unitario y peso total verificable por presentación |
| `implementacion/dimer/outputs/phase-01-3-prompt-config.json` | Contexto y overrides de tools del agente con reglas de papas e IVA |
| `docs/superpowers/specs/2026-08-14-dimer-recuperacion-mccain-design.md` | Decisiones funcionales y rollback |

---

### Task 1: Generar previews deterministas

**Repo:** `suplai-platform` · rama `feat/dimer-mccain-recovery`

**Files:**
- Create: `scripts/dimer/preparar_recuperacion_mccain.py`
- Create: `implementacion/dimer/outputs/recuperacion-mccain-clientes.csv`
- Create: `implementacion/dimer/outputs/recuperacion-mccain-aliases.csv`
- Create: `implementacion/dimer/outputs/recuperacion-mccain-pesos.csv`
- Modify: `implementacion/dimer/outputs/phase-01-3-prompt-config.json`

**Interfaces:**
- Consumes: constantes aprobadas de clientes, SKUs, alias y pesos.
- Produces: tres CSV, JSON válido y resumen `clients=30 aliases=... weights=14`.

- [ ] **Step 1: Crear constantes de clientes y productos**

El script debe definir:

```python
CLIENTS = {
    58: "Luisa", 65: "Juan", 70: "Luis", 73: "Gerardo", 74: "Eduardo",
    85: "Roberto", 86: "David", 90: "Agustín", 91: "Mónica", 95: "Hernán",
    98: "Christian", 102: "Juan", 106: "Daniel", 110: "Juan", 113: "Angélica",
    119: "Cristian", 128: "Luis", 144: "Gloria", 146: "Patricio", 148: "Nicolás",
    151: "Claudia", 156: "Ricardo", 160: "Rafael", 164: "María", 171: "Víctor",
    173: "David", 174: "José", 182: "María", 185: "Juan", 186: "Verónica",
}

WEIGHTS = {
    "110A74011": (8, 2.25),
    "110A11121": (8, 2.25),
    "110111091": (6, 2.5),
    "1000007407": (6, 2.5),
    "110113101": (6, 2.5),
    "1000006570": (5, 2.5),
    "110A10641": (4, 2.5),
    "110A18951": (6, 1.5),
    "1000010226": (5, 2.5),
    "1000002300": (6, 2.5),
    "11000509": (4, 2.5),
    "236110": (5, 2.5),
    "236211": (5, 2.5),
    "1000002889": (7, 2.5),
}
```

Los alias deben ser una lista de tuplas `(product_code, alias_raw, weight)` con peso `1.25` para alias exactos de medida/intención y `1.10` para variantes descriptivas:

```python
ALIASES = [
    ("110A74011", "kilo de 7", 1.25),
    ("110A74011", "papa 7", 1.25),
    ("110A74011", "papas 7mm", 1.25),
    ("110A74011", "tipo mcdonalds", 1.25),
    ("110A74011", "corte fast food", 1.10),
    ("110A11121", "corte fino 7", 1.25),
    ("110A11121", "papa fina 7mm", 1.25),
    ("110A11121", "mccain fina", 1.10),
    ("110111091", "kilo de 10", 1.25),
    ("110111091", "papa 10", 1.25),
    ("110111091", "papas 10mm", 1.25),
    ("110111091", "tradicional 10mm", 1.25),
    ("110113101", "kilo de 12", 1.25),
    ("110113101", "papa 12", 1.25),
    ("110113101", "papas 12mm", 1.25),
    ("110113101", "corte casero 12", 1.10),
    ("1000007407", "papa crocante 10", 1.10),
    ("1000007407", "papas que duran crocantes", 1.10),
    ("1000006570", "papas mccain onduladas", 1.25),
    ("1000006570", "corte ondulado", 1.10),
    ("110A10641", "papa decorativa", 1.10),
    ("110A18951", "papas sonrisa", 1.25),
    ("110A18951", "papas carita", 1.25),
    ("110A18951", "croquetas smiles", 1.10),
]
```

- [ ] **Step 2: Implementar normalización y validaciones**

```python
import re
import unicodedata

def normalize_alias(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)

def validate() -> None:
    assert len(CLIENTS) == 30
    assert len(set(CLIENTS)) == 30
    assert all(name and name == name.strip() for name in CLIENTS.values())
    assert len(WEIGHTS) == 14
    assert all(units > 0 and kg > 0 for units, kg in WEIGHTS.values())
    pairs = [(normalize_alias(alias), code) for code, alias, _ in ALIASES]
    assert len(pairs) == len(set(pairs))
    generic = {
        normalize_alias(alias): code
        for code, alias, weight in ALIASES
        if weight == 1.25 and alias.startswith(("kilo de", "papa "))
    }
    assert generic["kilode7"] == "110A74011"
    assert generic["kilode10"] == "110111091"
    assert generic["kilode12"] == "110113101"
```

- [ ] **Step 3: Generar CSVs**

Los headers exactos son:

```python
CLIENT_HEADERS = ["client_id", "nombre_de_pila", "target_group", "action"]
ALIAS_HEADERS = ["product_code", "alias_raw", "alias_norm", "weight", "action"]
WEIGHT_HEADERS = ["product_code", "unidades_por_bulto", "peso_referencia_kg", "peso_total_kg", "action"]
```

Cada cliente usa `target_group=Grupo 1`, `action=set_first_name_and_replace_membership`.
Cada alias usa `action=upsert`.
Cada peso usa `peso_total_kg = unidades_por_bulto * peso_referencia_kg`, `action=set_reference_weight`.

- [ ] **Step 4: Actualizar el JSON de prompt**

Leer `phase-01-3-prompt-config.json`, preservar `identidad`, `reglas_negocio` y `agent_phone_number`, y dejar al final de `contexto` el bloque completo `JERGA DE PAPAS CONGELADAS PARA RESTAURANTES` + `CONSULTAS POR KILO E IVA` aprobado en el spec. Para toda cotización de formato, el bloque debe ordenar la secuencia `search_products → get_product_by_code` y prohibir inferir pesos desde el nombre o memoria. El script debe reemplazar el bloque previo desde el heading para que una regeneración actualice las reglas sin duplicarlas.

Agregar además `tools_descripciones.search_products` y `tools_descripciones.get_product_by_code` con el mismo contrato: búsqueda para resolver un SKU y segundo lookup obligatorio para recuperar la presentación estructurada. Son overrides por tenant en `public.distribuidoras`, no cambios de runtime.

- [ ] **Step 5: Ejecutar y verificar artefactos**

```bash
python3 scripts/dimer/preparar_recuperacion_mccain.py
python3 -m py_compile scripts/dimer/preparar_recuperacion_mccain.py
python3 -m json.tool implementacion/dimer/outputs/phase-01-3-prompt-config.json >/dev/null
wc -l implementacion/dimer/outputs/recuperacion-mccain-*.csv
```

Expected:

- clientes: 31 líneas con header;
- alias: 25 líneas con header;
- pesos: 15 líneas con header;
- JSON válido;
- cero escrituras de BD.

---

### Task 2: Aplicar configuración a Supabase

**Scope:** datos productivos en `dimer` y solo `public.distribuidoras.contexto` / `tools_descripciones` para tenant `dimer`.

**Precondition:** los tres CSV existen, los conteos coinciden y el usuario aprobó el diseño.

- [ ] **Step 1: Repetir tenant y obtener snapshot**

Antes del primer write, informar: `Tenant confirmado: dimer`.

La consulta de snapshot debe devolver:

- membresía de `etiqueta_id=2`;
- `nombre_de_pila` de IDs objetivo;
- alias de los 14 SKUs;
- pesos actuales;
- contexto actual;
- agendas para `Grupo 1` + `prueba_01`.

- [ ] **Step 2: Ejecutar una única transacción**

La transacción debe:

1. Validar que `Grupo 1` es `id=2` o resolver su ID por nombre.
2. Validar que la etiqueta `Grupo 1` es `id=2` o resolver su ID por nombre.
3. Validar los 30 IDs, estado activo y teléfono `^569[0-9]{8}$`.
4. Validar que los 14 SKUs existen, tienen la presentación esperada y conservan `es_pesable=false`.
5. Actualizar `nombre_de_pila` con `UPDATE ... FROM (VALUES ...)`.
6. Eliminar solo las relaciones de la etiqueta resuelta que no estén en los 30 IDs.
7. Insertar las 30 relaciones con `ON CONFLICT (client_id, etiqueta_id) DO NOTHING`.
8. Actualizar `peso_referencia_kg` solo para los 14 SKUs y verificar `unidades_por_bulto`; no modificar `es_pesable`.
9. Insertar/actualizar alias con conflicto `(alias_norm, product_code)`.
10. Reemplazar el bloque desde el heading en `public.distribuidoras.contexto`, preservando el contexto anterior.
11. Combinar en `public.distribuidoras.tools_descripciones` los overrides de `search_products` y `get_product_by_code`, preservando las demás tools.
12. Insertar una agenda puntual si no existe una equivalente:

```sql
INSERT INTO dimer.agenda (
  grupo_id, meta_plantilla_id, tipo, hora_envio,
  fecha_programada, dynamic_params, activo, origen
)
SELECT
  g.id, mp.id, 'puntual', TIME '11:00',
  DATE '2026-08-17', '[]'::jsonb, true, 'dimer-mccain-recovery'
FROM dimer.grupos g
JOIN public.distribuidoras d ON d.schema_name='dimer'
JOIN public.meta_plantillas mp
  ON mp.tenant_id=d.id AND lower(mp.template_name)='prueba_01'
WHERE lower(trim(g.nombre))='grupo 1'
  AND NOT EXISTS (
    SELECT 1 FROM dimer.agenda a
    WHERE a.grupo_id=g.id
      AND a.meta_plantilla_id=mp.id
      AND a.tipo='puntual'
      AND a.fecha_programada=DATE '2026-08-17'
      AND a.hora_envio=TIME '11:00'
  );
```

Toda validación debe producir una excepción antes de mutar si el conteo esperado no coincide.

- [ ] **Step 3: No enviar mensajes**

El apply termina con la agenda creada. No llamar manualmente al sender ni a Meta.

---

### Task 3: Verificación integral

- [ ] **Step 1: Consulta consolidada post-apply**

Verificar en una sola llamada:

- `Grupo 1` = 30 miembros;
- 30/30 con `nombre_de_pila`;
- 30/30 teléfonos `569` válidos;
- cero miembros anteriores fuera de la lista;
- 24 alias objetivo presentes;
- 14 pesos presentes y positivos;
- 14/14 productos objetivo con `es_pesable=false`;
- heading del prompt aparece exactamente una vez;
- overrides de `search_products` y `get_product_by_code` presentes;
- una agenda puntual activa para 2026-08-17 11:00;
- plantilla `prueba_01` mantiene `variable_columns=["nombre"]`.

- [ ] **Step 2: Validar formato comercial y semántica de peso**

Con la lista vigente, verificar que los datos necesarios para describir el formato sean coherentes y que los productos sigan siendo no pesables:

```sql
SELECT p.product_code, p.nombre, pp.precio_unidad,
       p.unidades_por_bulto, p.peso_referencia_kg,
       p.es_pesable,
       p.unidades_por_bulto * p.peso_referencia_kg AS peso_total_presentacion_kg
FROM dimer.productos p
JOIN dimer.precios_productos pp
  ON pp.product_code=p.product_code AND pp.lista_precios_id=1
WHERE p.product_code IN ('110A74011','110111091','110113101');
```

Expected:

- 7 mm Fast Food: `8 × 2,25 kg`, total descriptivo `18 kg`, `es_pesable=false`;
- 10 comercial / 9 mm caja: `6 × 2,5 kg`, total descriptivo `15 kg`, `es_pesable=false`;
- 12 mm Casero: `6 × 2,5 kg`, total descriptivo `15 kg`, `es_pesable=false`;
- `precio_unidad` es el precio final con IVA de la unidad mínima de venta; la verificación no calcula ni persiste precio por 1 kg.

- [ ] **Step 3: Validación humana**

En backoffice `3000` + backend `8000`:

1. Abrir tenant `dimer`.
2. Confirmar 30 miembros en Grupo 1.
3. Confirmar agenda puntual `prueba_01`, fecha 17/08 y hora operacional 11:00.
4. En laboratorio: `¿A cuánto está el kilo de 7mm?`.
5. Verificar que responde con McCain Fast Food 7 mm, `8 bolsas de 2,25 kg`, precio final de caja con IVA y SKU, sin dividir el precio por 18.
6. Consultar `papa de 10` y verificar equivalencia con McCain Tradicional 9 mm.
7. Consultar `necesito 20 kilos de 7mm` y verificar que explica el formato disponible y pregunta cuántas cajas o unidades quiere, sin convertir 20 kg a bolsas.
8. Simular objeción de precio y verificar alternativa equivalente sin descuento inventado.

- [ ] **Step 4: Revisar diff**

```bash
git status --short
git diff -- docs/superpowers implementacion/dimer scripts/dimer
```

No crear commit ni PR salvo pedido explícito del usuario.
