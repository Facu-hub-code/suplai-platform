# ETL de alta de catálogo — plan de implementación

> **Deprecado el 2026-10-21.** No retomar estas tareas. El job no llama al worker. La categoría volvió al alta del spec 127.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un SKU nuevo abre una fila de pipeline, un playbook (Tokin en Almaro) completa la ficha vía una sola API, y el catálogo se prende solo si el checklist cierra.

**Architecture:** Extraer y Transformar siguen en el promote del 127. Enriquecer, Cargar y Publicar viven en `erp/enriquecimiento/`. El worker llama al servicio. El Grok Bot llama a un MCP privado montado en `/mcp-catalogo`, que es cáscara de ese servicio. El MCP de Claude no cambia.

**Tech Stack:** Python 3, FastAPI, asyncpg, MCP SDK ya usado en `mcp_server/`, pytest, Grok Bot con skill en `.grok/skills/`.

## Global Constraints

- Rama `feat/erp-alta-catalogo-automatica` en `backend-supabase` y en `suplai-platform`, desde `origin/main`. No implementar en `main`.
- El MCP de Claude sigue en 52 tools. `proponer_ficha` no entra ahí.
- CI no llama a Grok, a Tokin ni a la base. Puerto 6543 y `statement_cache_size=0` si algún test de integración toca Postgres. Los tests de este plan no lo hacen.
- No se reescriben productos que ya existen. No se abre fila para ellos. No se corre `corregir_umv_default_viejo` sin filtro de SKU.
- El precio no se escribe en la carga. La conversión entra como texto y la parsea la API. `categoria_id` tiene que estar en la lista del tenant.
- Tope de 3 intentos si Tokin no tiene ficha. Tope de 20 filas por corrida del worker.
- Almaro es el único tenant con playbook `tokin`. El resto no llama al modelo.
- El job no elige categoría en ningún tenant. Sin playbook, el alta queda apagada y se avisa la categoría.
- Descripción que viene de Tokin no pasa por `agrega_hechos`. La que arma el promote antes del playbook, sí.

**Spec:** `docs/specs/128-etl-alta-catalogo.md`.

---

### Task 1: Tabla y repositorio de la fila

**Files:**
- Create: `backend-supabase/sql/172_catalogo_alta.sql`
- Create: `backend-supabase/data_access/catalogo_alta.py`
- Test: `backend-supabase/tests/erp/test_catalogo_alta_repo_sql.py`

**Interfaces:**
- Consumes: nada del 128.
- Produces: `abrir(conn, schema, product_code, faltantes, playbook_id) -> None`, `reclamar(conn, schema, product_code) -> dict | None`, `cerrar(conn, schema, product_code, etapa, propuesta, faltantes, intentos, error) -> None`, `listar_abiertas(conn, schema, limite) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
from data_access.catalogo_alta import SQL_ABRIR, SQL_RECLAMAR, SQL_CERRAR

def test_reclamar_solo_toma_una_fila_abierta_en_transformado():
    assert "etapa = 'transformado'" in SQL_RECLAMAR
    assert "abierto" in SQL_RECLAMAR
    assert "RETURNING" in SQL_RECLAMAR

def test_abrir_no_pisa_una_fila_existente():
    assert "ON CONFLICT" in SQL_ABRIR
    assert "DO NOTHING" in SQL_ABRIR
```

- [ ] **Step 2: Run test to verify it fails**

Run from `backend-supabase`: `./venv/bin/pytest tests/erp/test_catalogo_alta_repo_sql.py -v`  
Expected: FAIL, `catalogo_alta` no existe.

- [ ] **Step 3: Write minimal implementation**

`sql/172_catalogo_alta.sql`:

```sql
CREATE TABLE IF NOT EXISTS core.catalogo_alta (
    id bigserial PRIMARY KEY,
    schema_name text NOT NULL,
    product_code text NOT NULL,
    etapa text NOT NULL,
    faltantes text[] NOT NULL DEFAULT '{}',
    playbook_id text,
    propuesta jsonb,
    intentos int NOT NULL DEFAULT 0,
    error text,
    abierto boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT catalogo_alta_unica UNIQUE (schema_name, product_code),
    CONSTRAINT catalogo_alta_etapa_chk CHECK (
        etapa IN ('transformado', 'enriqueciendo', 'publicado', 'apagado')
    )
);

CREATE INDEX IF NOT EXISTS catalogo_alta_abiertas_idx
    ON core.catalogo_alta (schema_name)
    WHERE abierto;

ALTER TABLE core.catalogo_alta ENABLE ROW LEVEL SECURITY;
```

`data_access/catalogo_alta.py` exporta esas tres cadenas y funciones que hacen `conn.fetchrow` / `conn.execute` contra `core.catalogo_alta`. `schema_name` y `product_code` son parámetros `$1` y `$2`. No se interpolan en el SQL. `SQL_RECLAMAR` es:

```sql
UPDATE core.catalogo_alta
SET etapa = 'enriqueciendo', updated_at = now()
WHERE schema_name = $1
  AND product_code = $2
  AND etapa = 'transformado'
  AND abierto
RETURNING schema_name, product_code, faltantes, playbook_id, intentos, etapa, abierto;
```

`SQL_ABRIR` inserta `etapa = 'transformado'` con `ON CONFLICT (schema_name, product_code) DO NOTHING`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/test_catalogo_alta_repo_sql.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sql/172_catalogo_alta.sql data_access/catalogo_alta.py tests/erp/test_catalogo_alta_repo_sql.py
git commit -m "Agrega la fila de pipeline del alta de catálogo."
```

---

### Task 2: Playbook Tokin y parser de conversión

**Files:**
- Create: `backend-supabase/erp/enriquecimiento/playbooks/tokin.py`
- Create: `backend-supabase/erp/enriquecimiento/conversiones.py`
- Create: `backend-supabase/tests/erp/fixtures/tokin_14617.json`
- Test: `backend-supabase/tests/erp/test_conversiones_tokin.py`

**Interfaces:**
- Consumes: nada.
- Produces: `refs_arc(code: str) -> list[str]`, `parsear_conversiones(conversion_1: str | None, conversion_2: str | None) -> dict`, `objetivo_tokin(code: str) -> str`, `PLAYBOOKS = {"tokin": ...}`, `playbook_de(schema: str) -> str | None`. `playbook_de("almaro")` es `"tokin"`. Cualquier otro schema devuelve `None`.

El dict de `parsear_conversiones` tiene `umv_tipo`, `upd`, `dpb`, `upb`. Valores que no salen del texto van `None`.

- [ ] **Step 1: Write the failing test**

`tests/erp/fixtures/tokin_14617.json` es el recorte de la ficha leída el 2026-10-21: `productReference` `ARC-1014617`, `productName` `Polenta Noel 490gr.`, `brand` `Noel`, `description` `Polenta Noel 490gr.`, specs `Display (1 Unidad)` y `Bulto (30 Unidades)`.

```python
import json
from pathlib import Path
from erp.enriquecimiento.conversiones import parsear_conversiones
from erp.enriquecimiento.playbooks.tokin import objetivo_tokin, playbook_de, refs_arc

def test_polenta_queda_en_unidad_con_bulto_30():
    ficha = json.loads(Path("tests/erp/fixtures/tokin_14617.json").read_text())
    specs = {s["name"]: s["values"][0] for s in ficha["specificationGroups"][0]["specifications"]}
    factores = parsear_conversiones(specs["Descripción de Conversión  1"], specs["Descripción de Conversión  2"])
    assert factores == {"umv_tipo": "unidad", "upd": None, "dpb": None, "upb": 30}

def test_display_de_varias_unidades():
    factores = parsear_conversiones("Display (12 Unidades)", "Bulto (4 Displays)")
    assert factores == {"umv_tipo": "display", "upd": 12, "dpb": 4, "upb": None}

def test_texto_ajeno_no_escribe_factores():
    assert parsear_conversiones("caja por mayor", None) == {
        "umv_tipo": None, "upd": None, "dpb": None, "upb": None,
    }

def test_referencias_de_14617_empiezan_por_el_arc_completo():
    assert refs_arc("14617")[0] == "ARC-1014617"

def test_el_objetivo_pide_la_referencia_exacta_y_no_calcula_el_bulto():
    texto = objetivo_tokin("14617")
    assert "ARC-1014617" in texto
    assert "productReference" in texto
    assert "No calcules unidades por bulto" in texto
    assert "listar_categorias_suplai" in texto

def test_solo_almaro_tiene_playbook():
    assert playbook_de("almaro") == "tokin"
    assert playbook_de("demo") is None
```

El nombre de la spec en el fixture lleva dos espacios antes del número, como lo devuelve Tokin: `Descripción de Conversión  1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/erp/test_conversiones_tokin.py -v`  
Expected: FAIL, módulo no existe.

- [ ] **Step 3: Write minimal implementation**

`conversiones.py` usa los mismos regex que `.cursor/skills/validar-umv-tokin/scripts/comparar_umv_tokin.py`:

```python
import re

DISPLAY_RE = re.compile(r"display\s*\(\s*(\d+)\s*unidad", re.I)
BULTO_RE = re.compile(r"bulto\s*\(\s*(\d+)\s*(display|unidad)", re.I)

def parsear_conversiones(conversion_1, conversion_2) -> dict:
    vacio = {"umv_tipo": None, "upd": None, "dpb": None, "upb": None}
    display = DISPLAY_RE.search(conversion_1 or "")
    bulto = BULTO_RE.search(conversion_2 or "")
    if not display and not bulto:
        return vacio
    upd = dpb = upb = None
    umv = None
    if display:
        n = int(display.group(1))
        if n > 1:
            umv = "display"
            upd = n
        else:
            umv = "unidad"
    if bulto:
        n = int(bulto.group(1))
        if bulto.group(2).lower().startswith("display"):
            dpb = n
        else:
            upb = n
        umv = umv or "unidad"
    return {"umv_tipo": umv, "upd": upd, "dpb": dpb, "upb": upb}
```

`refs_arc` se copia de la skill. `objetivo_tokin` devuelve el texto de la sección «Playbook Tokin» del spec, con `{refs}` reemplazado por una referencia por línea. `playbook_de` es el dict `{"almaro": "tokin"}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/test_conversiones_tokin.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add erp/enriquecimiento tests/erp/fixtures/tokin_14617.json tests/erp/test_conversiones_tokin.py
git commit -m "Parsea la conversión de Tokin sin dejar que el modelo calcule el bulto."
```

---

### Task 3: Cargar la propuesta y publicar

**Files:**
- Create: `backend-supabase/erp/enriquecimiento/servicio.py`
- Test: `backend-supabase/tests/erp/test_enriquecimiento_servicio.py`

**Interfaces:**
- Consumes: `parsear_conversiones`, `playbook_de`, `faltantes_estructurales` de `erp/services/alta_checklist.py`.
- Produces: `aplicar_propuesta(repo, catalogo, propuesta: dict) -> dict` con claves `etapa`, `escrito`, `faltantes`. `reclamar_alta(repo, schema, product_code) -> dict | None`.

`propuesta` tiene `schema_name`, `product_code`, `encontrado`, `referencia`, `url`, `nombre`, `descripcion`, `marca`, `image_url`, `conversion_1`, `conversion_2`, `categoria_id`.

`catalogo` es un objeto de test con `ficha`, `categorias: set[int]`, `precio_minimo`, `escrito: dict`. No es la base.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from erp.enriquecimiento.servicio import aplicar_propuesta, AltaCerrada

class Repo:
    def __init__(self):
        self.fila = {
            "schema_name": "almaro", "product_code": "14617", "abierto": True,
            "etapa": "enriqueciendo", "intentos": 0, "playbook_id": "tokin", "faltantes": ["categoria"],
        }
        self.guardado = None
    async def leer(self, schema, code):
        return self.fila if self.fila["product_code"] == code else None
    async def guardar(self, **kwargs):
        self.guardado = kwargs
        self.fila.update(kwargs)

class Catalogo:
    def __init__(self):
        self.precio_minimo = 1088.79
        self.categorias = {12}
        self.escrito = None
        self.avisos = []
        self.nombre_erp = "POLENTA NOEL 30 X 490 G"
    async def escribir(self, **kwargs):
        self.escrito = kwargs
    async def avisar(self, faltantes):
        self.avisos.extend(faltantes)
    async def vectorizar(self, product_code):
        self.vectorizado = product_code

def propuesta(**extra):
    base = {
        "schema_name": "almaro", "product_code": "14617", "encontrado": True,
        "referencia": "ARC-1014617", "url": "https://tokin.example/search",
        "nombre": "Polenta Noel 490gr.", "descripcion": "Polenta Noel 490gr.",
        "marca": "Noel", "image_url": "https://tokin.vtexassets.com/arquivos/ids/284846/a.jpg",
        "conversion_1": "Display (1 Unidad)", "conversion_2": "Bulto (30 Unidades)",
        "categoria_id": 12,
    }
    base.update(extra)
    return base

@pytest.mark.asyncio
async def test_tokin_pisa_el_nombre_y_no_el_precio():
    repo, catalogo = Repo(), Catalogo()
    salida = await aplicar_propuesta(repo, catalogo, propuesta())
    assert catalogo.escrito["nombre"] == "Polenta Noel 490gr."
    assert catalogo.escrito["upb"] == 30
    assert "precio" not in catalogo.escrito
    assert salida["etapa"] == "publicado"
    assert repo.fila["abierto"] is False

@pytest.mark.asyncio
async def test_fila_cerrada_no_escribe():
    repo, catalogo = Repo(), Catalogo()
    repo.fila["abierto"] = False
    with pytest.raises(AltaCerrada):
        await aplicar_propuesta(repo, catalogo, propuesta())
    assert catalogo.escrito is None

@pytest.mark.asyncio
async def test_categoria_que_no_esta_en_la_lista_se_rechaza():
    repo, catalogo = Repo(), Catalogo()
    salida = await aplicar_propuesta(repo, catalogo, propuesta(categoria_id=999))
    assert catalogo.escrito["categoria_id"] is None
    assert "categoria" in salida["faltantes"]
    assert "categoria" in catalogo.avisos
    assert salida["etapa"] == "apagado"

@pytest.mark.asyncio
async def test_tercer_miss_cierra_apagado():
    repo, catalogo = Repo(), Catalogo()
    repo.fila["intentos"] = 2
    salida = await aplicar_propuesta(repo, catalogo, propuesta(encontrado=False, nombre=None, descripcion=None, marca=None, image_url=None, conversion_1=None, conversion_2=None, categoria_id=None, referencia=None, url=None))
    assert catalogo.escrito is None
    assert salida["etapa"] == "apagado"
    assert repo.fila["intentos"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/erp/test_enriquecimiento_servicio.py -v`  
Expected: FAIL, `servicio` no existe.

- [ ] **Step 3: Write minimal implementation**

`aplicar_propuesta`:

1. Lee la fila. Si no está o `abierto` es false, lanza `AltaCerrada`.
2. Si `encontrado` es false, suma `intentos`. Si llega a 3, guarda `etapa=apagado`, `abierto=false`, `error=sin_tokin` y no llama a `catalogo.escribir`. Si no, guarda `etapa=transformado`, `abierto=true`, `error=sin_tokin`.
3. Si `encontrado` es true, parsea las conversiones. Descarta `categoria_id` que no esté en `catalogo.categorias`. Descarta `image_url` que no empiece con `https://`. Arma el escrito con nombre, descripcion, marca, image_url, factores y categoria_id. No incluye precio.
4. Recalcula huecos con `faltantes_estructurales` sobre el nombre de Tokin y los factores, más `precio` si `precio_minimo` es None, más `precio_bajo` si es menor a `PRECIO_PISO`, más `categoria` si `categoria_id` quedó None. La descripción de Tokin no se manda a `agrega_hechos`. Si la descripción viene vacía, el hueco `descripcion` se queda.
5. `etapa` es `publicado` si no hay huecos y `apagado` si hay. `abierto=false` en los dos casos. Llama a `catalogo.escribir` y después a `repo.guardar`.
6. `catalogo.escribir` también recibe `caja_semantica`, calculada con `caja_de` de `alta_checklist.py` a partir de los factores. `marca` se guarda como un alias. Si el producto ya tiene 2 aliases, no se agrega.
7. Después de escribir, `catalogo.vectorizar(product_code)` y `catalogo.avisar(faltantes)`. El test de la categoría rechazada afirma que `avisar` recibió `"categoria"`.

`erp/enriquecimiento/catalogo_pg.py` es el adaptador real. Su SQL de update lista `nombre`, `descripcion`, `image_url`, `umv_tipo`, `unidades_por_display`, `displays_por_bulto`, `unidades_por_bulto`, `caja_semantica`, `en_catalogo`. No menciona `precio_unidad` ni `stock`. Un test en el mismo archivo afirma eso sobre la constante `SQL_FICHA`. El `WHERE` es `product_code = $n`. La vectorización llama a `vectorizar_productos(schema, [product_code])`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/test_enriquecimiento_servicio.py tests/erp/test_conversiones_tokin.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add erp/enriquecimiento/servicio.py tests/erp/test_enriquecimiento_servicio.py
git commit -m "La carga de Tokin pisa la ficha abierta y publica con el checklist."
```

---

### Task 4: El promote abre la fila y deja de elegir categoría

**Files:**
- Modify: `backend-supabase/erp/services/erp_product_promote_service.py` (el loop que empieza en `categoria_id = await elegir_categoria_id`)
- Modify: `backend-supabase/erp/services/erp_sync_service.py` (`alta_catalogo_en_job`)
- Modify: `backend-supabase/tests/erp/services/test_erp_product_promote.py`
- Test: el mismo archivo

**Interfaces:**
- Consumes: `abrir` de `data_access/catalogo_alta.py`, `playbook_de`.
- Produces: cada SKU insertado abre una fila. `categorias_asignadas` del promote pasa a 0. El job ya no llama a `reintentar_categorias_recientes`.

- [ ] **Step 1: Write the failing test**

En `test_erp_product_promote.py`, el test que hoy espera categoría 3 pasa a esperar que el insert de `product_categories` no se llame y que `en_catalogo` (`params[10]`) sea `False` aunque `elegir_categoria_id` devolviera un id. El test de dry-run del SKU `4013` espera `categoria` dentro de `faltantes`.

```python
def test_el_promote_no_asigna_categoria(self):
    # el mock de elegir_categoria_id puede seguir en 3: el loop no lo llama
    assert "product_categories" not in " ".join(sql for sql, _ in self.inserts)
```

Adaptar los nombres al estilo de la clase existente. El assert nuevo es: ninguna SQL del alta contiene `product_categories`, y el parámetro de `en_catalogo` es `False`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/erp/services/test_erp_product_promote.py -v`  
Expected: FAIL, el promote todavía inserta `product_categories`.

- [ ] **Step 3: Write minimal implementation**

En el loop de `promote_erp_products_bulk`, borrar el llamado a `elegir_categoria_id` y el `INSERT` de `product_categories`. Después de armar `faltan`, agregar siempre `"categoria"` si no está. `visible` sigue siendo `en_catalogo_de(extra) and not faltan`, así que un alta nueva queda apagada por la categoría.

Después de `created.append(sku)`, llamar `abrir` con la conexión del promote, los `faltantes` y `playbook_de(schema)`.

Si `playbook_de(schema)` no es None, no llamar a `_avisar` por el código `categoria` ni por el ticket `[ERP_CATALOGO] imagenes`. Esos dos los abre Publicar si siguen vacíos después del enriquecimiento. El resto de los códigos se avisan igual.

En `alta_catalogo_en_job`, sacar `reintentar_categorias_recientes`. `categorias_asignadas` queda en 0.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/services/test_erp_product_promote.py tests/erp/services/test_alta_checklist.py -v`  
Expected: PASS. Los tests viejos que contaban una categoría asignada se actualizan en este mismo paso para esperar 0 y `en_catalogo` false.

- [ ] **Step 5: Commit**

```bash
git add erp/services/erp_product_promote_service.py erp/services/erp_sync_service.py tests/erp/services/test_erp_product_promote.py
git commit -m "El alta nueva deja la categoría para el playbook y abre la fila de pipeline."
```

---

### Task 5: API interna

**Files:**
- Create: `backend-supabase/routers/catalogo_alta.py`
- Modify: `backend-supabase/main.py` (el `include_router`)
- Test: `backend-supabase/tests/erp/test_catalogo_alta_api.py`

**Interfaces:**
- Consumes: `aplicar_propuesta`.
- Produces: `POST /interno/catalogo-alta/propuesta`. Header `Authorization: Bearer {CATALOGO_ETL_TOKEN}`. Body = la propuesta de la Task 3. `401` si el token no coincide. `409` si `AltaCerrada`. `200` con `{etapa, escrito, faltantes}`.

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

def test_sin_bearer_responde_401(client):
    respuesta = client.post("/interno/catalogo-alta/propuesta", json={"product_code": "1"})
    assert respuesta.status_code == 401

def test_fila_cerrada_responde_409(client, token):
    respuesta = client.post(
        "/interno/catalogo-alta/propuesta",
        json={"schema_name": "almaro", "product_code": "14617", "encontrado": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 409
```

El `client` de este test construye una app mínima con el router y un `aplicar_propuesta` falso que lanza `AltaCerrada`. No levanta `main.py` entero.

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/erp/test_catalogo_alta_api.py -v`  
Expected: FAIL, ruta no registrada.

- [ ] **Step 3: Write minimal implementation**

El router compara el bearer con `os.environ["CATALOGO_ETL_TOKEN"]` en tiempo constante (`hmac.compare_digest`). Delega en `aplicar_propuesta`. No escribe SQL. Registrar el router en `main.py` junto al resto de `include_router`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/test_catalogo_alta_api.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add routers/catalogo_alta.py main.py tests/erp/test_catalogo_alta_api.py
git commit -m "Expone una sola puerta para guardar la ficha que trae Tokin."
```

---

### Task 6: MCP privado

**Files:**
- Create: `backend-supabase/mcp_server/catalogo_privado.py`
- Modify: `backend-supabase/mcp_server/main.py` (montar la app en `/mcp-catalogo`, sin pasar por `aplicar_meta` ni por `VISIBLES`)
- Test: `backend-supabase/tests/test_mcp_catalogo_privado.py`
- Test: `backend-supabase/tests/test_mcp_superficie.py` (sin cambios de número; tiene que seguir en 52)

**Interfaces:**
- Consumes: `reclamar_alta`, `aplicar_propuesta`, y una función `listar_categorias_suplai(schema) -> list[dict]` que arma `ruta` con `parent_id`.
- Produces: tools `leer_faltantes(schema, product_code)`, `listar_categorias_suplai(schema)`, `proponer_ficha(propuesta)`.

- [ ] **Step 1: Write the failing test**

```python
from mcp_server.catalogo_privado import TOOLS
from mcp_server.superficie import VISIBLES

def test_el_mcp_privado_tiene_tres_tools():
    assert set(TOOLS) == {"leer_faltantes", "listar_categorias_suplai", "proponer_ficha"}

def test_claude_no_recibe_la_tool_de_la_ficha():
    assert "proponer_ficha" not in VISIBLES
    assert len(VISIBLES) == 52
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_mcp_catalogo_privado.py tests/test_mcp_superficie.py -v`  
Expected: FAIL en el archivo nuevo. `test_mcp_superficie` sigue PASS.

- [ ] **Step 3: Write minimal implementation**

`catalogo_privado.py` construye un `MCPServer` aparte con las tres tools. `leer_faltantes` llama a `reclamar`. Si no hay fila, devuelve `{abierto: false}`. Si hay, devuelve la ficha, los huecos y `objetivo_tokin(product_code)` cuando el playbook es `tokin`. `listar_categorias_suplai` lee `id, name, parent_id` sin `LIMIT` y agrega `ruta` uniendo los nombres desde la raíz. `proponer_ficha` llama a `aplicar_propuesta` y traduce `AltaCerrada` a un error de tool, no a un insert.

Montar `streamable_http_app` de ese servidor en `/mcp-catalogo` dentro de `mcp_server/main.py`. El bearer es el mismo `CATALOGO_ETL_TOKEN`. No llamar a `aplicar_meta` sobre este servidor.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_mcp_catalogo_privado.py tests/test_mcp_superficie.py tests/test_mcp_esquema_gemini.py -v`  
Expected: PASS. Gemini sigue viendo 52 tools.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/catalogo_privado.py mcp_server/main.py tests/test_mcp_catalogo_privado.py
git commit -m "El agente de enriquecimiento lee huecos y guarda la ficha por un MCP aparte."
```

---

### Task 7: Worker con modelo intercambiable

**Files:**
- Create: `backend-supabase/erp/enriquecimiento/worker.py`
- Modify: `backend-supabase/erp/services/erp_sync_service.py` (`alta_catalogo_en_job` llama al worker después del promote)
- Test: `backend-supabase/tests/erp/test_enriquecimiento_worker.py`

**Interfaces:**
- Consumes: `listar_abiertas`, `reclamar_alta`, `aplicar_propuesta`, `playbook_de`.
- Produces: `enriquecer_altas(schema, modelo, limite=20) -> dict` con `tomadas` y `errores`. `modelo` es `async def modelo(contexto: dict) -> dict` y devuelve una propuesta. Si `playbook_de(schema)` es None, no llama a `modelo`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from erp.enriquecimiento.worker import enriquecer_altas

class Repo:
    def __init__(self, filas):
        self.filas = filas
        self.reclamos = []
    async def listar_abiertas(self, schema, limite):
        return [f for f in self.filas if f["etapa"] == "transformado"][:limite]
    async def reclamar(self, schema, code):
        self.reclamos.append(code)
        fila = next(f for f in self.filas if f["product_code"] == code)
        fila["etapa"] = "enriqueciendo"
        return fila

@pytest.mark.asyncio
async def test_sin_playbook_no_llama_al_modelo():
    llamadas = []
    async def modelo(contexto):
        llamadas.append(contexto)
        return {}
    repo = Repo([{"product_code": "1", "etapa": "transformado"}])
    salida = await enriquecer_altas("demo", modelo, repo, limite=20)
    assert llamadas == []
    assert salida["tomadas"] == 0

@pytest.mark.asyncio
async def test_almaro_toma_como_maximo_20():
    filas = [{"product_code": str(i), "etapa": "transformado"} for i in range(25)]
    repo = Repo(filas)
    async def modelo(contexto):
        return {"schema_name": "almaro", "product_code": contexto["product_code"], "encontrado": False}
    salida = await enriquecer_altas("almaro", modelo, repo, limite=20)
    assert salida["tomadas"] == 20
    assert len(repo.reclamos) == 20
```

El segundo test parchea `erp.enriquecimiento.worker.aplicar_propuesta` con un `AsyncMock`. El worker reclama con `repo.reclamar`, que ejecuta el mismo `SQL_RECLAMAR` de la Task 1. No abre otra puerta de escritura.

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/erp/test_enriquecimiento_worker.py -v`  
Expected: FAIL, `worker` no existe.

- [ ] **Step 3: Write minimal implementation**

`enriquecer_altas` vuelve de inmediato si `playbook_de(schema)` es None o si `os.getenv("CATALOGO_ETL_MODELO") == "off"`. Si no, lista hasta `limite` filas, reclama cada una y llama a `modelo` con `{schema, product_code, objetivo}`. La propuesta vuelve a `aplicar_propuesta`. Una excepción del modelo deja la fila en `transformado`, suma el error a la salida y sigue con la siguiente. No corta el job.

El adaptador real, `modelo_grok`, vive en el mismo archivo y solo se usa si `CATALOGO_ETL_MODELO` no es `off`. Hace `POST https://api.x.ai/v1/chat/completions` con `Authorization: Bearer {XAI_API_KEY}`, el objetivo como system, y tools cuyos nombres son las tres del MCP. La implementación de cada tool llama al servicio, no al HTTP del MCP. El modelo y el timeout salen de `XAI_MODEL` y `XAI_TIMEOUT_S` (default 60). Este adaptador no se llama desde los tests. Un test aparte afirma que, con `CATALOGO_ETL_MODELO=off`, `modelo_grok` no se instancia.

`alta_catalogo_en_job` llama `enriquecer_altas(schema, modelo_grok)` después de `promote_erp_products_bulk` y de `escribir_precios_faltantes`. No llama a `reintentar_categorias_recientes`.

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/pytest tests/erp/test_enriquecimiento_worker.py tests/erp/services/test_erp_product_promote.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add erp/enriquecimiento/worker.py erp/services/erp_sync_service.py tests/erp/test_enriquecimiento_worker.py
git commit -m "El job enriquece las altas abiertas de Almaro y deja pasar al resto."
```

---

### Task 8: Skill y guion del Grok Bot

**Files:**
- Create: `suplai-platform/.grok/skills/enriquecer-ficha/SKILL.md`
- Modify: `suplai-platform/docs/grok-bot/README.md` (una fila en la tabla de skills y el prompt de la prueba)

**Interfaces:**
- Consumes: las tres tools del MCP privado y el objetivo que devuelve `leer_faltantes`.
- Produces: la skill que el Bot ejecuta en la prueba humana del spec.

- [ ] **Step 1: Write the skill**

`.grok/skills/enriquecer-ficha/SKILL.md`:

```markdown
---
name: enriquecer-ficha
description: >-
  Completa un alta de catálogo abierto con la ficha de Tokin y una categoría
  de Suplai. Usar cuando hay una fila abierta en core.catalogo_alta.
---

# Enriquecer ficha

Trabajás un solo producto por turno. No escribís SQL. No usás el MCP de Supabase para actualizar `productos`. No usás el MCP de Claude.

## Orden

1. `leer_faltantes` con el schema y el `product_code` del mensaje. Si `abierto` es false, parás y lo decís.
2. Seguí el campo `objetivo` al pie de la letra. En Almaro ese texto manda a buscar en Tokin por las referencias `ARC-10…`, quedarte con el `productReference` exacto y copiar nombre, descripción, marca, foto del ítem UNIDAD y el texto de las dos conversiones.
3. Si ninguna referencia coincide, `proponer_ficha` con `encontrado=false` y el resto vacío. No busques otro producto por el nombre ni en la web.
4. `listar_categorias_suplai`. Elegí un id de esa lista. Si hay hoja y padre, la hoja. Si ninguna cierra, `categoria_id` null.
5. `proponer_ficha` con la referencia, la URL, los textos copiados y el `categoria_id`. No calculés unidades por bulto. No mandes precio.

## Qué responder

La etapa que devolvió `proponer_ficha`, el `productReference` usado, y los huecos que quedaron. Si la fila ya estaba cerrada, decilo y no vuelvas a proponer.
```

En `docs/grok-bot/README.md`, agregar la fila de la skill y el prompt:

```
Hay un alta abierto en almaro para el producto {code}. Seguí la skill enriquecer-ficha. No escribas SQL. No uses el MCP de Supabase para actualizar productos.
```

El `{code}` es un SKU que el promote acaba de crear, no uno de los 13 ya cargados. El worker tiene que estar con `CATALOGO_ETL_MODELO=off` durante esta prueba, como dice el spec.

- [ ] **Step 2: Verificar que el texto del objetivo quedó en un solo lugar**

El objetivo largo vive en `playbooks/tokin.py`. La skill le dice al Bot que obedezca el campo `objetivo` de `leer_faltantes`. No copies el objetivo otra vez en la skill. Si los dos textos divergen, gana el de `leer_faltantes`.

- [ ] **Step 3: Commit en platform**

```bash
git add .grok/skills/enriquecer-ficha/SKILL.md docs/grok-bot/README.md docs/specs/128-etl-alta-catalogo.md docs/specs/127-alta-automatica-catalogo-erp.md docs/superpowers/plans/2026-10-21-etl-alta-catalogo.md
git commit -m "Documenta el ETL del alta y la skill con la que el Grok Bot lo prueba."
```

Este commit es del repo `suplai-platform`. Los commits de las tasks 1 a 7 son del repo `backend-supabase`.
