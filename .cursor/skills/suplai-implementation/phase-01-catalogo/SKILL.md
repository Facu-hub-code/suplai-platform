---
name: suplai-implementation-phase-01
description: Fase 1 catálogo — Excel a CSV de productos enriquecidos y carga a Supabase. Usar tras preflight OK.
---

# Fase 1 — Catálogo

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- [ ] Excel en `implementacion/{schema}/inputs/`
- [ ] Confirmar columna de precio: **Precio Final** (reventa) salvo que el implementador diga Neto
- [ ] Para multi-hoja (Colormix): consolidar todas las hojas

## Output

1. **`phase-01-productos.csv`** (obligatorio) — headers en `implementacion/_template/outputs/phase-01-productos.csv`
2. **`phase-01-lista-precios-{lista_precios_id}.csv`** (un archivo independiente por cada lista de precios, ej. `phase-01-lista-precios-1.csv`, `phase-01-lista-precios-2.csv`, etc., obligatorios si solo hay un precio en Excel)

## Inferencia (por fila)

| Regla | Campo |
|-------|--------|
| `(B/12)`, `x12`, `12x` en nombre | `unidades_por_bulto` |
| Sin patrón | `1` |
| Default | `unidad_minima_de_venta=unidad`, `umv_tipo=unidad`, `en_catalogo=true` |
| Hoja Excel | `categoria_1`, `fuente_hoja` |
| NLP en nombre | `categoria_2`..`categoria_4` |
| Top ~20% marcas líderes del rubro | `rotacion_index` 0.75–0.95 |
| Resto | Pareto hacia 0.1 |
| LLM | `aliases` (pipe-separated en CSV), `descripcion` (ver reglas abajo), `image_url` placeholder |
| Sin stock en Excel | `stock` 10–500 según rotación |
| Simulación | `is_mock=true` en CSV |


## Reglas estrictas para `descripcion` (generación inicial sin búsqueda web)

> ⚠️ Esta descripción es provisoria. La Fase 1.2 la mejora con búsqueda web solo para los N productos seleccionados. Por eso la calidad inicial importa: el resto nunca se enriquecerá.

1. **Longitud**: 10 a 25 palabras. Una sola oración breve.
2. **Cero fluff/marketing**: Prohibido usar palabras como `delicioso`, `irresistible`, `suave`, `ideal`, `perfecto`, `descubre`, `disfruta`, `cautivará`, `atractivo`, `rotación rápida`, ni mencionar kioscos, ventas o márgenes.
3. **Formato directo**: Empezar con el sustantivo de la categoría del producto.
   - ✅ `Chocolate con leche relleno de crema de frutilla, marca Cofler, 30 g.`
   - ✅ `Ravioles de pollo y verdura, marca DeViano, 900 g, x12 unidades.`
   - ❌ `Descubre los irresistibles Ravioles DeViano, ideales para compartir en familia...`
4. **Contenido permitido**: marca, sabor, formato físico (peso, presentación, unidades por bulto). Sin adornos.
5. **Sin contexto inventado**: No incluir afirmaciones sobre comportamiento del consumidor, sugerencias de venta ni beneficios percibidos.

## Listas de precios mock

Crear 4 listas con multiplicadores 1.00, 1.15, 0.90, 0.85 sobre `precio_lista_1` por SKU.

## Validación antes de carga

- SKUs únicos
- `precio_lista_1` > 0
- Contar filas → anotar en manifest

Pedir: **"Revisá phase-01-productos.csv y confirmá carga"**.

## Carga MCP (tras confirmación)

Orden sugerido:

1. `INSERT` `{schema}.listas_precios` (4 filas) — anotar IDs, todas deben ser visibles (`listas_precios.activa = true` AND `listas_precios.es_publica = true`)
2. `INSERT` `{schema}.productos` en lotes
3. `INSERT` `{schema}.precios_productos` desde cada uno de los archivos `phase-01-lista-precios-*.csv`
4. `INSERT` `{schema}.productos_aliases` (un alias por fila o split)
5. **Re-vectorización (CRÍTICO)**: Realizar un request `POST` a `https://web-production-f544f.up.railway.app/{schema}/productos/vectorize` enviando el listado de códigos de productos insertados en el body (como un JSON Array de strings, ej: `["PROD01", "PROD02"]`). Esto encolará la vectorización y permitirá al agente de IA entender los productos.

Contrastar columnas con `list_tables` verbose. No insertar columnas inexistentes.

## Verificación

- `COUNT(*)` productos = filas CSV (± rechazos documentados)
- `SELECT product_code, nombre, precio_unidad FROM {schema}.precios_productos pp JOIN {schema}.productos p LIMIT 3`

## Cierre

- `manifest.fases.01.estado = cargado`
- Detectar **marca_lider** (marca con más SKUs) → `manifest.marca_lider`
- Invitar Fase 2

## Colormix

Ver `docs/implementacion/colormix-notas.md`.
