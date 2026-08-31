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
- [ ] Si `manifest.modo = demo`: recorte **80–100 SKUs** descriptivos (ver abajo). Catálogo completo → `inputs/catalogo-completo.csv`

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

## Modo demo — recorte 80–100 (obligatorio si `modo: demo`)

El CSV de carga **no** es el Excel entero. Elegir **entre 80 y 100** SKUs que permitan una demo de WhatsApp creíble (el PdV pide lo que vende el negocio, no un dump).

1. Exportar todos los SKUs con precio a `inputs/catalogo-completo.csv`.
2. Clasificar por línea comercial (gaseosas, vinos, cervezas, limpieza, etc.) usando nombre + notas de la reunión.
3. Armar el recorte con esta prioridad:
   - **Marca líder / exclusiva** (la que el cliente quiere empujar): 20–35%.
   - **Una muestra de cada línea** que el negocio declara (≥3 SKUs si la línea existe en el Excel).
   - **Formatos que se piden por chat** (caja/bulto vs unidad; 500 ml vs 2,25 L).
   - **Marcas de zona** y **competencia** que el PdV nombra.
   - Completar hasta 80–100 **sin** saturar una sola familia (máx. ~8 SKUs de la misma marca no líder, salvo que sea la exclusiva).
4. Descartar Precio Final ≤ 0, combos vacíos y filas sin nombre.
5. Si el origen ya tiene ≤100 SKUs con precio: no recortar.
6. Nutrir **cada** fila del recorte (no dejar descripciones de una palabra): `descripcion` 10–25 palabras, aliases con sinónimos locales de UMV, categorías 1–4, `unidades_por_bulto` del Excel o del patrón `NxM` del nombre.

Anotar `manifest.demo.productos_cargados` y `filas_csv`. Fase 1.2 enriquece **estos mismos** 80–100 (no omitir).

## Validación antes de carga

- SKUs únicos
- `precio_lista_1` > 0
- En demo: `80 ≤ filas ≤ 100` (o todos si el origen es más chico)
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
