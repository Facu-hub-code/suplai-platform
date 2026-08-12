# Spec 034 — Biblioteca de ideas en dos niveles + gates configurables por theme

**Estado:** Implementado en ramas feature — migración `backend/sql/100_ideas_gates_dos_niveles.sql` aplicada en Supabase el 2026-08-11 (7 ideas generales, 34 schemas con `gate_config`)
**Fecha:** 2026-08-11
**Tipo:** Cross-repo (backend + backoffice; platform docs)
**Relaciona:** SPEC-026 (ciclo inteligente, themes y señales), SPEC-028 (nearby v1), SPEC-029 (agendas 1:1), SPEC-031 (send calendar)

**Ramas:**

| Repo | Rama | PR |
|------|------|----|
| `suplai-platform` | `feat/ideas-gates-dos-niveles` (este spec) | — |
| `backend-supabase` | `feat/ideas-gates-dos-niveles` | — |
| `product-management-app` | `feat/ideas-gates-dos-niveles` | — |

---

## 1) Objetivo

Darle al motor de estrategias una **capa de control configurable** sobre cuándo usar cada theme, evitando mensajes genéricos ("con este clima…") en las agendas 1:1:

1. **Gates por theme**: cada idea de la biblioteca lleva una configuración tipada (formulario por theme) que define **cuándo el theme es elegible y con qué peso/probabilidad**. Ejemplos: clima solo si va a llover > X mm; mapa solo si el lugar está a ≤ Y metros; feriado con probabilidad 100 %.
2. **Plan + revalidar**: el planner asigna theme al planificar el ciclo (el calendario/preview muestra el theme probable); **antes de cada envío** se re-evalúan las señales frescas y se puede cambiar de theme o cancelar el envío si la señal cayó.
3. **Biblioteca en dos niveles**: ideas **generales de Suplai** (curadas, globales, `public`) e ideas **propias de cada distribuidora** (schema tenant). Una distribuidora puede **copiar una general y personalizarla** (copy + gate).

## 2) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Config del gate | `gate_config JSONB` en la idea, validado por **modelos Pydantic tipados por theme** (discriminated union por `theme`); UI = formulario por theme | Campos con semántica clara y validación fuerte; el form del BO se renderiza según el theme. Descartado: JSON libre (mala UX, sin validación) y columnas dedicadas por parámetro (una migración por cada gate nuevo). |
| Dos niveles de biblioteca | Nueva tabla **`public.suplai_skeleton_ideas`** (general, curada por Suplai) + la existente `{schema}.estrategia_skeleton_ideas` (propias). Copiar = INSERT en la tenant con `source_suplai_idea_id` | Separación física limpia: lo global no se mezcla con lo del tenant y se versiona una sola vez. Descartado: flag `scope` en la tabla tenant (duplica la "general" en N schemas, como hace hoy el seed de `sql/91`, y no permite actualizarla centralmente). |
| Copiar y personalizar | Endpoint `POST /{schema}/estrategia-skeleton-ideas/copy-from-general` que clona copy + `gate_config` y guarda `source_suplai_idea_id` | Fork explícito y trazable; la distribuidora edita su copia sin tocar la general. Descartado: override parcial por referencia (merge de configs difícil de razonar en el BO). |
| Momento de evaluación | **Plan + revalidar**: `pick_theme_for_client` (scores × gates) al abrir ciclo / materializar agendas; **re-evaluación en el envío** (`dispatch_reserved` y `agenda_sender` Motor B) con señales frescas | El preview/calendario muestra el theme probable y el envío nunca sale con una señal caída. Descartado: solo al enviar (el calendario no anticipa nada) y solo al planificar (lluvia/stock cambian día a día). |
| Resultado del gate en revalidación | Si el theme asignado ya no pasa su gate → elegir el **siguiente theme elegible** del pool aprobado; si ninguno pasa → fallback `purchase_habit`; si el gate es `require` estricto y no hay fallback → **skip** del envío (release de budget) | El envío siempre tiene un motivo comercial válido; nunca sale "con este clima" porque sí. |
| Feriado 100 % | Gate `holiday` con `override: true`: si hay feriado en la ventana configurada y el pool tiene HSM `holiday` aprobado, **fuerza** ese theme (probabilidad 100 %) con copy temático + aviso de que no se trabaja ese día | Pedido de producto explícito; es la señal más determinística. |
| Clima real (lluvia) | Cambiar de *current weather* a **forecast** de OpenWeather (5 day / 3 h); gate con `rain_mm_threshold` y `window_hours`. El ángulo comercial es "el preventista no va a poder pasar, pedí por acá", no la descripción del clima | La descripción actual ("nubes dispersas") genera mensajes raros; los mm previstos son accionables. Descartado: One Call API 3.0 (requiere plan pago). |
| Cache de clima | Cache in-memory por (lat/lon redondeados a 1 decimal, ventana) con TTL 3 h | Evita 1 request por cliente por envío (cohorts de cientos de PdV comparten ciudad). |
| Radio nearby | Default **300 m** (era 800) + `near_distance_m` (default 120 m ≈ misma cuadra) que da boost fuerte; ambos configurables en el gate | 800 m mete lugares irrelevantes; "en la misma cuadra" es el caso que convierte. |
| Distancia nearby | Persistir `distance_m` por place en `clients.metadata.nearby` (Google lo devuelve; hoy se descarta) | Sin distancia no se puede aplicar el boost por cercanía. |
| Stock-out (ERP + ML) | Nuevo gate sobre `purchase_habit`: `use_ml_stock_out` llama a sales-engine `predict-replenishment`; si hay stock-out previsto en ≤ `stockout_window_days`, boost fuerte y el contexto pasa a ser "te estás por quedar sin {producto}" | Reutiliza el modelo existente de sales-engine (ya corre retrain diario 04:00). Descartado: theme nuevo `stock_out` (requiere HSM nuevo en Meta; con el gate alcanza para v1 y el copy sale del slot `{{2}}`). |
| Agenda 1:1 (Motor B) | `agenda_sender` deja de hardcodear `purchase_habit`: carga `intelligence_config` + gates de la estrategia y llama a `pick_theme_for_client` + `resolve_body_params` con el theme ganador | Hoy el Motor B ignora todo el sistema de themes (bug funcional detectado en esta investigación). |
| Una sola capa de inteligencia | Wizard sin toggles de señales: la biblioteca/gates es la única config; al guardar se **deriva** `intelligence_config.signals` desde los themes del pool (para learning notify). Paso Inteligencia = explicación del loop. | Duplicaba la misma decisión en wizard vs salida; `pick_theme` ya ignora los flags. |
| Sin promos en wizard | Se retira el paso Promos del flujo de estrategia (no se linkean desde create/edit). Tabla/API `estrategia_promociones` quedan sin uso activo. | No alimentaban mensaje ni atribución del ciclo; solo cobertura. |
| Gobierno de la biblioteca general | v1: seed por migración + solo lectura desde el BO tenant; CRUD para Suplai en el panel admin queda para v2 | Desbloquea el valor sin construir permisos de administración global ahora. |

### Shape de `gate_config` por theme (v1)

```jsonc
// weather
{
  "theme": "weather",
  "enabled": true,
  "base_weight": 0,                // sin lluvia prevista el theme no compite
  "rain_mm_threshold": 4,          // mm acumulados en la ventana
  "window_hours": 24,              // mirar el forecast de las próximas N horas
  "boost_weight": 8,               // score si supera el umbral
  "require": true                  // si no llueve, el theme queda inelegible (no baja a base)
}

// nearby_map
{
  "theme": "nearby_map",
  "enabled": true,
  "radius_m": 300,
  "near_distance_m": 120,          // "misma cuadra"
  "base_weight": 1,                // hay lugares dentro del radio
  "near_boost_weight": 6,          // el mejor lugar está a ≤ near_distance_m
  "priority_place_types": ["school", "university"]   // tipos que activan el boost
}

// holiday
{
  "theme": "holiday",
  "enabled": true,
  "override": true,                // probabilidad 100 % si aplica
  "days_before": 2,                // enviar hasta N días antes del feriado
  "mention_no_work_day": true      // el copy debe avisar que ese día no se trabaja
}

// purchase_habit (+ stock ERP/ML)
{
  "theme": "purchase_habit",
  "enabled": true,
  "base_weight": 2,
  "use_ml_stock_out": false,       // solo tiene efecto con ERP conectado
  "stockout_window_days": 7,
  "stockout_boost_weight": 7
}

// seller
{
  "theme": "seller",
  "enabled": true,
  "base_weight": 1.5
}
```

Los defaults reproducen (mejorados) los boosts hardcodeados actuales de `pick_theme_for_client`. Los `system_fixed` (`cart_open`, `engaged_no_buy`) no llevan gate: los dispara el estado del cliente, como hoy.

## 3) Alcance explícito

### Incluido (v1)

- Tabla `public.suplai_skeleton_ideas` + seed con las 7 ideas actuales (copy mejorado por theme: clima = lluvia/preventista, feriado = temático + no se trabaja).
- `gate_config` + `source_suplai_idea_id` en `{schema}.estrategia_skeleton_ideas`; modelos Pydantic tipados por theme.
- Endpoints: listar biblioteca general, copiar general → tenant, CRUD tenant con `gate_config` validado.
- Motor de gates: `evaluate_theme_gates(schema, client_id, gate_configs)` → scores/elegibilidad; reemplaza los boosts hardcodeados de `pick_theme_for_client`.
- Forecast de lluvia (OpenWeather 5d/3h) con cache; `distance_m` persistido en nearby; radio 300 m default.
- Gate stock-out vía sales-engine `predict-replenishment` (solo tenants con ERP conectado).
- **Revalidación pre-envío** en `dispatch_reserved` y en `agenda_sender` Motor B (que además deja de hardcodear `purchase_habit`).
- Preview/calendario (SPEC-031): mostrar theme probable por cliente + estado del gate.
- BO: biblioteca con tabs **Generales (Suplai)** / **Mis ideas**, botón "Copiar y personalizar", formulario de gate por theme.

### Fuera de alcance (con motivo)

- CRUD admin de la biblioteca general (v1 se gobierna por migración/seed; v2 panel Suplai).
- Theme nuevo `stock_out` con HSM propio (el gate sobre `purchase_habit` cubre el caso sin pasar por aprobación Meta).
- Aprendizaje automático de pesos desde `theme_stats` (los gates son manuales en v1; el score histórico sigue sumando como hoy).
- Ediciones sobre la biblioteca general que se propaguen a copias ya hechas (el fork es independiente por diseño).

## 4) Orden de implementación

1. **backend** — migración `sql/9X_ideas_gates_dos_niveles.sql` (tabla public + columnas tenant + seed + backfill `distance_m` no aplica, se llena a futuro).
2. **backend** — modelos `gate_config` + endpoints biblioteca general/copy + CRUD con validación.
3. **backend** — motor de gates (`estrategias_gates.py`) + forecast clima + distancia nearby + stock-out; refactor `pick_theme_for_client`.
4. **backend** — revalidación pre-envío en `estrategias_dispatch_service` y `agenda_sender` (Motor B).
5. **backoffice** — tabs biblioteca + copiar/personalizar + formularios de gate por theme + theme probable en calendario.
6. **platform** — este spec + actualización del historial en SPEC-026.

Merge: **backend → backoffice → platform docs**. Un PR por repo sobre `feat/ideas-gates-dos-niveles`.

## 5) Migración de base de datos

Archivo: `backend-supabase/sql/9X_ideas_gates_dos_niveles.sql` (numerar al crear).

- **Nueva** `public.suplai_skeleton_ideas`: mismo shape que la tenant (`theme`, `title`, `body_text`, `variable_slots`, `header_type`, `header_image_url`, `buttons_spec`, `role`, `activo`) + `gate_config JSONB NOT NULL DEFAULT '{}'` + `version INT DEFAULT 1`.
- **Alter** `{schema}.estrategia_skeleton_ideas` (loop schemas activos, patrón `sql/91`):
  - `ADD COLUMN IF NOT EXISTS gate_config JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `ADD COLUMN IF NOT EXISTS source_suplai_idea_id INTEGER NULL` (sin FK cross-schema; integridad por aplicación)
- **Seed** `public.suplai_skeleton_ideas` con las 7 ideas (copys nuevos + `gate_config` defaults de §2).
- **Backfill**: las ideas tenant existentes quedan con `gate_config = '{}'` → el motor aplica defaults por theme en runtime (equivalente al comportamiento actual).
- **Rollback**: `DROP TABLE public.suplai_skeleton_ideas; ALTER TABLE {schema}.estrategia_skeleton_ideas DROP COLUMN gate_config, DROP COLUMN source_suplai_idea_id;` — riesgo bajo (columnas aditivas).

## 6) Plan de prueba en CI/CD

- `backend/tests/test_estrategias_gates.py` (nuevo): unit por gate — lluvia sobre/bajo umbral, `require`, nearby con `distance_m` dentro/fuera de `near_distance_m`, holiday override + `days_before`, stock-out con mock de sales-engine, defaults con `gate_config` vacío.
- `backend/tests/test_estrategias_skeleton_library.py`: copy-from-general (clona copy + gate + `source_suplai_idea_id`), validación Pydantic rechaza gate de otro theme.
- Ajustar `test_estrategias_variable_resolver.py`, `test_estrategias_cycle_service.py`, `test_estrategias_signals.py` a la nueva firma (scores → gates).
- Nuevo test de revalidación en `test_estrategias_dispatch_service.py`: theme caído → fallback; `require` sin fallback → skip + release de budget.
- Checks existentes de estrategias/agendas deben seguir verdes.
- Gap: forecast OpenWeather y Places live sin E2E automatizado → mock httpx en unit + smoke manual (§7).

## 7) Plan de prueba humana (antes del PR)

| Servicio | Puerto |
|----------|--------|
| Backend | `8000` |
| Backoffice | `3000` (fijo — Maps SDK) |

```bash
# Terminal 1
cd backend-supabase && source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd product-management-app
BACKEND_URL=http://localhost:8000 npm run dev
```

Tenant sugerido: `demo` (tiene estrategias y clientes geolocalizados).

1. Abrir Estrategias → **Biblioteca de ideas**: ver tabs "Generales (Suplai)" y "Mis ideas".
2. Copiar la general de clima → editar umbral a 2 mm y el copy → guardar. Verificar en BD `source_suplai_idea_id` y `gate_config`.
3. Crear estrategia con pool que incluya clima + feriado + mapa; abrir el calendario y verificar:
   - panel **Plantillas materializadas** (nombre Meta + theme + status);
   - por PdV, el **HSM del theme probable** (no solo plantilla legacy de agenda).
4. Forzar señales: insertar un feriado mañana en `distribuidora_calendar_events` → el preview debe pasar ese cliente a `holiday` (override 100 %).
5. Simular envío (dispatch dry-run o agenda de prueba a número propio): verificar que sin lluvia prevista **no** sale el theme clima, y que el mensaje del theme ganador usa el contexto correcto (no "con este clima").
6. Con ERP conectado (o mock de sales-engine local en `8001`): activar `use_ml_stock_out` y verificar boost + contexto "te estás por quedar sin…".
7. Verificar skip: estrategia solo con theme clima `require: true` y sin lluvia → el envío se salta y el ledger hace release.
8. Wizard: confirmar que **no** hay paso Promos ni toggles de señales; el paso Inteligencia solo explica el loop.

## 8) Historial

- 2026-08-11 — Draft inicial (gates por theme, plan + revalidar, biblioteca dos niveles con fork).
- 2026-08-11 — Simplificación wizard: una capa de inteligencia (biblioteca), sin promos; calendario muestra pool HSM materializado.
