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
Excel → Catálogo (F1) → Tags (F1.1) → Mejora Descripciones (F1.2) → Prompt Agente (F1.3) → Promos (F2) + Cross/Up (F3)
     → Red comercial (F4) → Flags clientes (F5)
     → Pedidos (F6) → Field App Setup (F6.1) → Conversaciones (F7) → Insights (F8)
     → Pruebas E2E (F9) → [opcional] Purga mock (F10)
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

- **Propósito**: Ejecutar la skill de enriquecimiento de descripciones comerciales y alias locales ([SKILL.md](../../.cursor/skills/enhance-descriptions/SKILL.md) / [skill-guide.md](../../.cursor/skills/enhance-descriptions/skill-guide.md)) para optimizar las fichas de productos frente al RAG del agente, eliminando relleno publicitario y agregando contexto técnico B2B.
- **Funcionamiento por Defecto**:
  - Se seleccionan automáticamente los **100 productos** más ambiguos de la base de datos usando el script [buscar_candidatos.py](../../scripts/fase-01-catalogo/buscar_candidatos.py):
    ```bash
    python scripts/fase-01-catalogo/buscar_candidatos.py --esquema {esquema} --limite 100
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
    python scripts/fase-01-catalogo/enriquecer_catalogo.py --esquema {esquema} --csv-entrada implementacion/{esquema}/inputs/candidatos_a_enriquecer.csv --csv-salida implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
    ```
  - **Persistir**: Tras el visto bueno del implementador (revisión manual del CSV), aplicar cambios a Supabase y re-vectorizar:
    ```bash
    python scripts/fase-01-catalogo/enriquecer_catalogo.py --esquema {esquema} --aplicar --csv-entrada implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
    ```
## Fase 1.3 — Personalización del Prompt del Agente

- Recopilar el rubro del distribuidor (ej. ferretería, consumo masivo) y restricciones del negocio (ej. "solo vende productos Arcor").
- Generar mediante LLM las definiciones estructuradas de `identidad`, `contexto` y el objeto JSON `reglas_negocio` del agente.
- Guardar el resultado propuesto en `outputs/phase-01-3-prompt-config.json`.
- Cargar/Actualizar la configuración en la tabla maestra `public.distribuidoras` para el tenant correspondiente (vía Supabase MCP).

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

## Fase 6.1 — Field App Setup

Habilita Suplai Field (gamificación del vendedor) con datos suficientes para que el ML
y el job diario de tareas funcionen desde el primer día.

**Pasos (en orden)**:

| Paso | Script | Resultado |
|------|--------|-----------|
| A | `preparar_pedidos_field.py` + `cargar_pedidos_field.py` | Pedidos Jun 2025–May 2026 (backbone + reciente) → ML tiene ≥3 compras por SKU ancla en 90 días |
| B | `habilitar_field.py` | `public.distribuidoras.metadata → {"field_app_enabled": true}` |
| C | `retrain_ml.py` | `POST {SALES_ENGINE_URL}/v1/tenants/{schema}/models/retrain` (silencioso si caído) |
| D | `setup_templates.py` | 3 templates activos: REACTIVAR_CLIENTE, CROSS_SELL_COMBO, REPOSICION_HABITO |
| E | `setup_objetivos.py` | 2 objetivos: SKU top rotación + grupo marca líder |
| F | `setup_torneo.py` | 1 torneo ACTIVO para el mes corriente |
| G | `seed_tareas_historicas.py` | Tareas completadas/parciales últimos 30 días laborables + ledger de puntos |
| H | `trigger_tareas.py --dias 6` | Tareas de hoy + próximos 5 días via backend ML real |

**Volúmenes**:
- Pedidos backbone: ~7 × N clientes (+ 3 recientes para activos)
- 20% clientes inactivos (>60 días sin compras) → disparan REACTIVAR_CLIENTE
- Tareas históricas seed: ~30 días × vendedores × 2-4 clientes × templates
- Distribución: 60% COMPLETADA / 25% PARCIAL / 15% PENDIENTE

**Scripts**: `platform/scripts/fase-06-1-field/`
**Skill**: `.cursor/skills/suplai-implementation/phase-06.1-field-setup/`

**Errores ML**: si el sales-engine está caído en Paso C, continuar; avisar al implementador.
CROSS_SELL_COMBO y REPOSICION_HABITO no se generarán hasta re-entrenar.

## Fase 7 — Conversaciones

- 3–5 mensajes por cliente (subset); 10–15 con actividad “hoy”.
- Tabla: `{tenant}.n8n_chat_histories`.
- Sandbox: probar agente solo con datos del tenant en implementación.

## Fase 8 — Insights / notificaciones

- 15–20 tickets en `ia_tickets` (o tabla de notificaciones del tenant).
- 60% abierto, 40% cerrado.
- Categorías: Calidad, Logística, Comercial, Administración.
- **Efecto cruzado:** alertas abiertas de Calidad/Logística deben tener mensaje entrante coherente en el chat del mismo cliente.

## Fase 9 — Pruebas E2E y Healthcheck

- **Propósito**: Ejecutar la validación integral y pruebas de conversación automáticas del agente conversacional ([SKILL.md](../../.cursor/skills/suplai-implementation/phase-09-e2e-testing/SKILL.md) / [skill-guide.md](../../.cursor/skills/suplai-implementation/phase-09-e2e-testing/skill-guide.md)) para auditar su correcto funcionamiento.
- **Healthcheck**:
  - Correr el script de validación de base de datos (que debería pasar exitosamente dado que todas las fases previas se completaron de manera correcta):
    ```bash
    python scripts/fase-09-e2e/healthcheck_schema.py --schema {esquema}
    ```
- **Suite de Pruebas E2E**:
  - Simular y validar los flujos típicos del agente conversacional (10 casos de prueba midiendo latencia y correcto llamado de herramientas):
    ```bash
    python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema}
    ```
- **Auditoría del Reporte**:
  - Revisar críticamente el reporte generado en `implementacion/{esquema}/outputs/reporte_e2e_{timestamp}.md` y realizar la validación de falsos negativos.

## Fase 10 — Purga mock

- Solo con columna `is_mock` y confirmación explícita `PURGE MOCK {schema}`.
- Borrado en cascada de todo registro mock; dejar tenant listo para producción.

## Prerequisito técnico

Migración: [`docs/implementacion/migrations/20260615_add_is_mock_columns_demo_and_tenants.sql`](migrations/20260615_add_is_mock_columns_demo_and_tenants.sql) — columna `is_mock` en `demo` (plantilla) y tablas tocadas por el onboarding. Aplicar vía Supabase MCP (sin `read_only`) o SQL Editor. Hasta aplicarla: CSV lleva `is_mock=true` y `manifest.yaml` registra `blocked: is_mock_migration` para Fase 10.

## Salidas por fase

Cada fase documenta **solo su CSV de salida** en `implementacion/{schema}/outputs/`. Ver plantillas en `implementacion/_template/outputs/`.
