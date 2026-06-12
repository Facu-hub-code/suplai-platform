# Flujo agéntico de implementación — Suplai Sales

Resumen operativo del documento *Flujo Agéntico de Implementación*. Fuente de verdad para las skills en `.cursor/skills/suplai-implementation/`.

## Objetivo

Poblar un tenant **recién registrado** (schema vacío) a partir del Excel de productos/precios del distribuidor. El resto de funcionalidades se completa con **datos mock contextuales** ligados a ese catálogo, para que back office, tienda y agente se vean operativos en la primera sesión.

## Constantes unificadas (addendum)

| Concepto | Valor |
|----------|-------|
| Clientes mock | 50 (40 con código ERP + 10 prospectos) |
| Vendedores mock | 3 |
| Zonas geográficas | 6 (2 por vendedor) |
| Promociones activas | 4 |
| Pedidos abiertos (bandeja) | 6–7 |
| Notificaciones / insights | 15–20 |
| Flag de simulación | `is_mock` (cuando exista en BD; ver prerequisito) |

## Pipeline (orden obligatorio)

```text
Excel → Catálogo (F1) → Tags (F1.1) → Mejora Descripciones (F1.2) → Promos (F2) + Cross/Up (F3)
     → Red comercial (F4) → Flags clientes (F5)
     → Pedidos (F6) → Conversaciones (F7) → Insights (F8)
     → [opcional] Purga mock (F9)
```

**Grafo comercial:** la misma marca/producto estrella debe aparecer en promos, up-sell y alertas de calidad (efecto cruzado).

## Fase 0 — Preflight

- Verificar `public.distribuidoras` y schema `{tenant}` vacío (`productos`, `clients` en 0).
- Registrar checks en `phase-00-preflight.csv`.

## Fase 1 — Catálogo y enriquecimiento

### Datos directos (Excel)

- SKU, nombre, precio lista base, stock (si viene).

### Datos inferidos (nombre del producto)

- `(B/12)`, `x12` → `unidades_por_bulto`
- Sin patrón → `1`
- UMV por defecto: `unidad` / `umv_tipo` = `unidad`
- Categorías 4 niveles (rubro + NLP en nombre)
- Aliases comerciales (LLM)
- `rotacion_index` y `mental_priority` (Pareto simulado)
- Descripción comercial
- Imagen placeholder por rubro
- `en_catalogo = true` siempre

### Listas de precios mock (si solo hay una columna de precio)

| Lista | Multiplicador sobre Lista 1 |
|-------|----------------------------|
| Lista 1 (Base) | 1.00 |
| Lista 2 (Minorista sugerido) | 1.15 |
| Lista 3 (Mayorista especial) | 0.90 |
| Lista 4 (Gran distribuidor) | 0.85 |

Tablas: `{tenant}.productos`, `listas_precios`, `precios_productos`, `productos_aliases`.

## Fase 1.1 — Tags Jerárquicos (Taxonomía)

- Consumir el endpoint `POST /{schema}/tags/propose-taxonomy` enviando como base el listado de productos de la Fase 1.
- Guardar la propuesta devuelta por la IA en un archivo JSON en `outputs/phase-01-1-propuesta-tags.json`.
- Enviar el JSON resultante al endpoint `POST /{schema}/tags/apply-proposed-taxonomy` para impactar la base de datos de tags jerárquicos (4 niveles).

## Fase 1.2 — Mejora de descripciones

- **Propósito**: Ejecutar la skill de enriquecimiento de descripciones comerciales y alias locales ([SKILL.md](file:///c:/Users/totot/OneDrive/Escritorio/Suplai_Sales/suplai-platform/.cursor/skills/enhance-descriptions/SKILL.md) / [skill-guide.md](file:///c:/Users/totot/OneDrive/Escritorio/Suplai_Sales/suplai-platform/.cursor/skills/enhance-descriptions/skill-guide.md)) para optimizar las fichas de productos frente al RAG del agente, eliminando relleno publicitario y agregando contexto técnico B2B.
- **Funcionamiento por Defecto**:
  - Se seleccionan automáticamente los **100 productos** más ambiguos de la base de datos usando el script [buscar_candidatos.py](file:///c:/Users/totot/OneDrive/Escritorio/Suplai_Sales/suplai-platform/scripts/buscar_candidatos.py):
    ```bash
    python scripts/buscar_candidatos.py --esquema {esquema} --limite 100
    ```
  - Esto guardará la lista en `implementacion/{esquema}/inputs/candidatos_a_enriquecer.csv`.
- **Interacción y Guardrails del IDE Agéntico**:
  - **Preguntar Siempre**: El IDE agéntico debe preguntar al implementador cuántos productos desea mejorar.
  - **Estimación de Tiempo**: Proveer una estimación clara del tiempo de ejecución (aproximadamente **3 segundos por producto**; por ejemplo, 100 productos tomarán unos **5 minutos**).
  - **Creación de `config.json`**: Ofrecer la creación de un archivo de configuración específico en `implementacion/{esquema}/config.json` previo a correr la skill para mejorar los resultados.
  - **Proponer Configuración**: Si el IDE tiene contexto de la distribuidora (ej. vinos con Vadra, ferretería con Colormix) o aprende de sus productos, propondrá proactivamente la estructura de este JSON (especificando dominios de búsqueda, términos de fallback, modo y reglas adicionales del catálogo).
- **Ejecución y Persistencia**:
  - **Dry Run**:
    ```bash
    python scripts/enriquecer_catalogo.py --esquema {esquema} --csv-entrada implementacion/{esquema}/inputs/candidatos_a_enriquecer.csv --csv-salida implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
    ```
  - **Persistir**: Tras el visto bueno del implementador (revisión manual del CSV), aplicar cambios a Supabase y re-vectorizar:
    ```bash
    python scripts/enriquecer_catalogo.py --esquema {esquema} --aplicar --csv-entrada implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
    ```

## Fase 2 — Promociones

- 4 promociones activas, `is_mock` cuando exista.
- Vigencia: inicio = hoy − 7 días, fin = hoy + 30 días.
- Matriz de tipos: % OFF, Total OFF, Precio fijo, % OFF en lista mayorista.
- Productos: top 4 por `rotacion_index` de Fase 1.

Tabla: `{tenant}.promociones_semanales`.

## Fase 3 — Cross-sell y up-sell

- Relaciones coherentes por marca/categoría.
- Tablas: `public.tenant_cross_sell_mappings`, `public.tenant_up_sell_mappings` (requiere `tenant_id` de `distribuidoras`).

## Fase 4 — Red comercial

- Input humano: **ciudad_base** (ancla geográfica).
- 3 vendedores mock, 6 zonas (`geo_zones` + `vendedor_geo_zones`), 50 clientes dispersos.
- Nombres de fantasía acordes al rubro del distribuidor.

## Fase 5 — Flags de clientes

- 80% con `codigo` ERP numérico; 20% prospectos (`codigo` = 0 o convención del tenant).
- WhatsApp: 60% validado, 40% sin validar / existe (usar columnas `whatsapp_*` del schema).

## Fase 6 — Pedidos

- Histórico: ~3 pedidos/cliente, estados cerrados, mar–may 2026.
- Vivos: 6–7 pedidos `abierto`/`pendiente` con fecha actual.
- Ítems en `items_pedido`; precio según `lista_precios_id` del cliente.

## Fase 7 — Conversaciones

- 3–5 mensajes por cliente (subset); 10–15 con actividad “hoy”.
- Tabla: `{tenant}.n8n_chat_histories`.
- Sandbox: probar agente solo con datos del tenant en implementación.

## Fase 8 — Insights / notificaciones

- 15–20 tickets en `ia_tickets` (o tabla de notificaciones del tenant).
- 60% abierto, 40% cerrado.
- Categorías: Calidad, Logística, Comercial, Administración.
- **Efecto cruzado:** alertas abiertas de Calidad/Logística deben tener mensaje entrante coherente en el chat del mismo cliente.

## Fase 9 — Purga mock

- Solo con columna `is_mock` y confirmación explícita `PURGE MOCK {schema}`.
- Borrado en cascada de todo registro mock; dejar tenant listo para producción.

## Prerequisito técnico

Migración backend pendiente: columna `is_mock` en tablas tocadas + endpoint/script de purga. Hasta entonces: CSV lleva `is_mock=true` y `manifest.yaml` registra `blocked: is_mock_migration` para Fase 9.

## Salidas por fase

Cada fase documenta **solo su CSV de salida** en `implementacion/{schema}/outputs/`. Ver plantillas en `implementacion/_template/outputs/`.
