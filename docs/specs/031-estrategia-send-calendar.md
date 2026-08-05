# Spec 031 — Calendario de envíos de estrategia (vista mes)

**Estado:** In progress (rev. 2 — solo mes + colores por validación Meta)  
**Fecha:** 2026-08-04  
**Tipo:** Cross-repo (backend + backoffice; platform docs)  
**Relaciona:** SPEC-029 (memoria + agendas 1:1 Motor B), SPEC-026 (ciclo inteligente / pool salida)

**Ramas:**

| Repo | Rama |
|------|------|
| `backend-supabase` | `feat/client-memory-wizard` |
| `product-management-app` | `feat/client-memory-wizard` |
| `suplai-platform` | `feat/client-memory-wizard` |

---

## 1) Objetivo

Después de crear o guardar una estrategia, el usuario ve un **calendario mensual con fechas concretas del mes** (estilo Google Calendar / mes) donde cada día muestra los **envíos proyectados a PdVs**. Hover y modal explican el **por qué** (estrategia, plantilla, horario, frecuencia, confianza). Varios envíos el mismo día/hora se listan juntos.

Los eventos usan **colores distintos** según el estado de validación Meta de la plantilla (creada pero aún no aprobada vs lista para enviar vs rechazada).

Complementa (no reemplaza) el preview lista de SPEC-029 y el “Calendario comercial” de feriados.

---

## 2) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Vista UI | **Solo mes** con días numerados del calendario (1…31) | La vista semana sin anclar a fechas reales no aporta. Descartado: grilla horaria semanal como default; toggle semana en v1. |
| Modelo de evento | 1 evento = 1 ocurrencia `(client_id, starts_at)` en un **día concreto** del mes | El usuario necesita ver “el lunes 11” no “lun genérico”. |
| Interacción día | Click en día → panel lateral / modal con lista de envíos de ese día + detalle why | En mes no hay eje horario continuo; el detalle vive al abrir el día. Hover en chip/evento del día muestra resumen del cluster. |
| Color del evento | Según `template_validation_status` de la plantilla asociada | Distinguir de un vistazo qué envíos dependen de plantillas aún no validadas por Meta. |
| Mapeo de color (v1) | Ver §7.2 | `pending`/`draft` = ámbar; `approved`/`skipped` = verde/brand; `rejected` = rojo; sin plantilla = gris. |
| Duración | No se dibuja bloque de 30′ en grilla horaria (no hay vista semana). El `starts_at` guarda fecha+hora para ordenar y mostrar “09:30” en la lista del día. | Simplifica UI mes. |
| Solapes | Mismo día: chips apilados / “+N”; al abrir el día, lista completa ordenada por hora | Varios PdV el mismo día es el caso real. |
| Razones (“por qué”) | Payload `reasons` en backend | Una sola fuente de verdad. |
| Plantilla del evento (v1) | La de `agenda.meta_plantilla_id` / pool asignado al materializar; status desde `estrategia_salida_templates.meta_status` (o Meta local) | El dispatch por theme es del ciclo; el calendario v1 proyecta schedule Motor B. Documentar que el envío real del ciclo puede elegir otro theme después. |
| Persistencia | Sin tabla nueva | Expandir agendas Motor B + metadata + status pool. |
| Entrada UX | Modal post-guardar + “Ver calendario” en estrategias | Cierra el loop de creación. |
| Interacción v1 | Solo lectura | Sin drag ni edición de slots. |

---

## 3) Alcance explícito

### Incluido (v1)

- Endpoint feed de calendario por estrategia para un **mes calendario** (fechas reales).
- Expansión de agendas Motor B a ocurrencias con `starts_at` en días concretos.
- Campo `template_validation_status` (+ color key) por evento.
- UI modal: **vista mes únicamente** (navegación mes anterior/siguiente).
- Chips/eventos en celdas de día; colores por estado de validación Meta.
- Hover resumen; click día → lista de envíos del día + why (estrategia, horario, frecuencia, confianza, plantilla + status).
- Leyenda de colores en el header del modal.
- Apertura al guardar/crear (tras `materialize-schedules`) y reabrir desde estrategias.
- Proxy BO + i18n mínimo (es).

### Fuera de alcance (v1)

- Vista semana / grilla horaria tipo timeline.
- Drag-and-drop / edición de slots.
- Simular picking theme-aware del dispatcher por cliente (calendario v1 = plantilla de la agenda materializada).
- Preview body Meta con variables resueltas.
- Histórico de dispatches ya enviados (v1.1).
- Unificar con calendario comercial (feriados).

---

## 4) Orden de implementación

1. **Backend:** `GET /{schema}/estrategias/{id}/send-calendar` (rango mes, reasons, `template_validation_status`) + tests.
2. **Backoffice proxy** + tipos.
3. **UI** `StrategySendCalendarModal` — mes + leyenda colores + panel día + why.
4. **Wiring** post-guardar + entrada desde `strategies-view`.
5. Docs (este spec).

**Merge:** backend → backoffice. Rama: `feat/client-memory-wizard` (o corte `feat/estrategia-send-calendar`).

---

## 5) Migración de base de datos

Sin migración de BD. Reutiliza:

- `{schema}.agenda` (Motor B)
- `{schema}.clients.metadata`
- `{schema}.estrategias` + `{schema}.estrategia_salida_templates` (`meta_status`, `meta_plantilla_id`, `template_name`)
- `public.meta_plantillas` (si hace falta nombre / sync)

---

## 6) API

### `GET /{schema}/estrategias/{id}/send-calendar`

**Query**

| Param | Tipo | Default | Notas |
|-------|------|---------|-------|
| `month` | `YYYY-MM` | mes actual (TZ tenant) | Preferido |
| `from` / `to` | date ISO | 1er y último día del `month` | Alternativa; máximo **45 días** |
| `tz` | string | TZ tenant | Para `starts_at` |

**Response (sketch)**

```json
{
  "ok": true,
  "estrategia_id": 12,
  "estrategia_nombre": "Reactivación Noroeste",
  "month": "2026-08",
  "from": "2026-08-01",
  "to": "2026-08-31",
  "timezone": "America/Argentina/Buenos_Aires",
  "summary": {
    "clients": 42,
    "events_in_range": 120,
    "confidence_counts": { "alta": 10, "media": 20, "baja": 12 },
    "template_status_counts": {
      "approved": 80,
      "pending_validation": 35,
      "rejected": 0,
      "unknown": 5
    }
  },
  "legend": [
    { "key": "approved", "label": "Plantilla aprobada / lista" },
    { "key": "pending_validation", "label": "Creada — pendiente de validación Meta" },
    { "key": "rejected", "label": "Plantilla rechazada" },
    { "key": "unknown", "label": "Sin plantilla / estado desconocido" }
  ],
  "events": [
    {
      "id": "agenda:123:2026-08-11",
      "agenda_id": 123,
      "client_id": 10,
      "client_name": "Asadería La Tradición",
      "starts_at": "2026-08-11T09:30:00-03:00",
      "local_date": "2026-08-11",
      "local_time": "09:30",
      "template_id": "uuid",
      "template_name": "promo_semana_v1",
      "template_validation_status": "pending_validation",
      "salida_template_id": 7,
      "salida_meta_status_raw": "pending",
      "frequency_bucket": "2_semanas",
      "confidence": {
        "frequency": "media",
        "schedule": "alta"
      },
      "reasons": {
        "strategy": {
          "summary": "Cliente del grupo de la estrategia",
          "grupo_id": 3,
          "grupo_nombre": "Zona Villa Allende"
        },
        "schedule": {
          "source": "memory",
          "detail": "Horario preferido 09:30 (source=hsm_reply)",
          "hora": "09:30",
          "confidence": "alta"
        },
        "frequency": {
          "source": "memory",
          "detail": "Frecuencia 2 semanas",
          "bucket": "2_semanas",
          "confidence": "media"
        },
        "template": {
          "source": "pool",
          "detail": "Plantilla del pool — pendiente de aprobación Meta",
          "validation_status": "pending_validation"
        }
      }
    }
  ]
}
```

### Normalización `template_validation_status`

| Origen (`estrategia_salida_templates.meta_status` u homólogo) | Status API |
|---------------------------------------------------------------|------------|
| `approved`, `skipped` | `approved` |
| `pending`, `draft`, `templates_pending` (si aplica) | `pending_validation` |
| `rejected` | `rejected` |
| null / no match | `unknown` |

Resolver plantilla del evento: `agenda.meta_plantilla_id` → join a `estrategia_salida_templates` de esa estrategia (mismo `meta_plantilla_id`) para leer `meta_status`; si no hay fila pool, marcar `unknown` o consultar estado local de `meta_plantillas` si existe.

**Reglas de expansión**

- Solo agendas `estrategia_id = :id` AND `activo` AND `client_id IS NOT NULL`.
- Recurrente + `dia_semana`: una ocurrencia por cada **fecha concreta** del mes cuyo weekday ∈ `dia_semana`, a `hora_envio`.
- Buckets 2 semanas / 1 mes: v1 proyecta todos los días de agenda del mes (posible sobredensidad); UI muestra hint “proyección según días de agenda”.
- Reasons memory vs default: igual lógica que materialize / preview-schedules.

**Errores:** 404 estrategia; 400 mes/rango inválido.

---

## 7) UI (backoffice)

### Componente

`StrategySendCalendarModal` en `product-management-app/components/`.

### Layout

1. Header: nombre estrategia · **Agosto 2026** · prev/next mes · cerrar.
2. KPIs: N clientes · eventos del mes · chips conf + **conteo pendientes de validación**.
3. **Leyenda de colores** (siempre visible).
4. **Grilla mes** (DOM…SÁB): cada celda = día del mes con número; eventos como chips (hora + nombre corto PdV) o “+N más”.
5. Color del chip = `template_validation_status` (§7.2).
6. Hover chip / cluster del día: lista corta (cliente · hora · plantilla · status).
7. Click día (o chip): panel con **todos** los envíos de ese `local_date` ordenados por hora; al seleccionar uno, bloques Why + badge de validación plantilla.

### 7.2 Colores (tokens sugeridos)

| Status | Color UI | Uso |
|--------|----------|-----|
| `approved` | Verde / brand primary | Lista para enviar (Meta OK o skipped local) |
| `pending_validation` | Ámbar / naranja | **Creada, aún sin validar** (foco producto) |
| `rejected` | Rojo suave | Hay que corregir plantilla |
| `unknown` | Gris muted | Sin link a pool / estado desconocido |

### Wiring

- Post create/update + `materialize-schedules` → abrir modal en el **mes actual**.
- `strategies-view` → “Ver calendario de envíos”.

### Accesibilidad

- No depender solo del color: icono o texto de status en chip/leyenda; focus teclado en días y lista.

---

## 8) Plan de prueba en CI/CD

- Backend: expansión a fechas concretas del mes (incl. bordes 1 y 31).
- Backend: mapeo `meta_status` → `template_validation_status` (pending → pending_validation, approved → approved).
- Backend: reasons memory vs default.
- BO: smoke manual (gap: sin E2E calendario obligatorio).
- Checks estrategias / agendas clásicas verdes.

---

## 9) Plan de prueba humana (antes del PR)

| Servicio | Puerto |
|----------|--------|
| Backend | `8000` |
| Backoffice | `3000` |

```bash
cd backend-supabase && source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

cd product-management-app
BACKEND_URL=http://localhost:8000 npm run dev
```

**Checklist**

1. Estrategia con pool: al menos una plantilla `pending` y otra `approved`.
2. Guardar → se abre **mes** con días numerados y chips en fechas reales.
3. Chips ámbar = pendiente validación; verdes = aprobadas; leyenda visible.
4. Click un día con varios envíos → lista completa; why con confianza.
5. Navegar mes siguiente/anterior.
6. Motor A no aparece; calendario feriados intacto.
7. Sin vista semana en la UI.

---

## 10) Criterios de aceptación

- [ ] Feed del mes con `local_date` / `starts_at` reales.
- [ ] Cada evento trae reasons, confidence y `template_validation_status`.
- [ ] UI **solo mes**; colores según validación Meta (pending ≠ approved).
- [ ] Hover/panel del día muestran todos los envíos de ese día.
- [ ] Post-guardar abre el calendario; se puede reabrir.
- [ ] Sin migración BD; sin vista semana en v1.

---

## 11) Relación con SPEC-029 y dispatcher

| Pieza | Rol |
|-------|-----|
| SPEC-029 materialize | Crea agendas 1:1 + hora/días; asigna una plantilla del pool a la agenda |
| SPEC-031 calendario | Visualiza esas ocurrencias en el mes + status de validación de esa plantilla |
| Dispatcher ciclo | En el envío real puede elegir **otro theme/plantilla** del pool por cliente — fuera del color/proyección v1 del calendario; documentar en UI si hace falta (“proyección de agenda; el ciclo puede rotar themes”) |

---

## 12) Riesgos / follow-ups

- Sobredensidad 2 semanas / 1 mes al proyectar todos los weekdays del mes.
- Color refleja plantilla de la **agenda**, no necesariamente la del próximo dispatch theme-aware.
- Meses densos: cap de chips por celda (“+N”) + lista completa al click.
- v1.1 opcional: vista día con eje horario; o overlay de dispatches `reserved`/`sent`.
