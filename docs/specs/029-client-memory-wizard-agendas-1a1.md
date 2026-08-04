# Spec 029 — Wizard de memoria de cliente + agendas 1:1 por estrategia

**Estado:** Implemented (F1 + F2 core)  
**Fecha:** 2026-08-04  
**Tipo:** Cross-repo (backend + backoffice + agent; platform docs)  
**Relaciona:** SPEC-028 (nearby v1), SPEC-026 (ciclo inteligente), agent SPEC-021 (agenda preferencias)

**Ramas:**

| Repo | Rama |
|------|------|
| `backend-supabase` | `feat/client-memory-wizard` |
| `product-management-app` | `feat/client-memory-wizard` |
| `agente-conversacional-multi_tenant` | `feat/client-memory-wizard` |
| `suplai-platform` | `feat/client-memory-wizard` |

---

## 1) Objetivo

Personalizar la comunicación PdV con **memoria de cliente** (cuándo contesta, frecuencia de compra, nearby configurable, top productos) vía wizard en el Mapa Comercial, y usar esa memoria en un **motor de estrategias** que materializa **agendas 1:1** por cliente — sin reemplazar el motor clásico de agendas de grupo.

## 2) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Orquestación enrich | Un endpoint **por paso** + wizard BO | Reintentos granulares y resumen visual por paso. Descartado: endpoint orquestador gordo; job async Railway (overkill vs loop concurrency 2). |
| Cuándo contesta | Híbrido: respuestas post-HSM → mensajes PdV → genérico + `ask_agent` (umbral default 5) | Máxima señal disponible; genérico no inventa confianza alta. |
| Persistencia horario | `clients.metadata.preferred_contact` | Desacopla preferencia del envío HSM. Descartado: seguir creando agenda+HSM preferred_contact. |
| Frecuencia | Reusar mediana/confianza Field → buckets 1s/2s/1m | Misma métrica que Field; evita divergencia. |
| Nearby tipos | Body opcional `place_types` en enrich-memory | UI configurable; default tipos v1.1. |
| Dos motores agenda | Clásico (`estrategia_id IS NULL`) vs estrategia (`estrategia_id NOT NULL`) | Producto pide agendas grupo vigentes + flota 1:1 inteligente en paralelo. |
| Pipeline estrategia | Stages separados **qué decir** / **cuándo enviar** | Contenido (themes/budget) vs schedule (hora+frecuencia). |
| Orden entrega | Fase 1 memoria → Fase 2 schedule | Sin memoria confiable el stage “cuándo” no aporta. |

## 3) Alcance explícito

### Fase 1 (esta entrega)

**Incluido**

- Shape `clients.metadata`: `preferred_contact`, `purchase_frequency`, `nearby` (ext), `top_products`.
- Endpoints: `enrich-preferred-contact`, `enrich-purchase-frequency`, `enrich-memory` (+ `place_types`), `enrich-top-products`; PUT preferred-contact (agente).
- Wizard Mapa Comercial 4 pasos + config + resumen visual (zona y 1:1).
- Tool agente `upsert_preference`: solo metadata; deprecar dependencia HSM preferred_contact.
- BO: marcar plantilla preferred_contact como deprecated.

**Fuera de alcance F1**

- Recalculo automático periódico de memoria.
- Borrado de agendas HSM preferred_contact legacy.

### Fase 2 (misma epic / follow-up inmediato)

**Incluido**

- Migración `agenda.estrategia_id` (+ `origen`).
- Stage **cuándo enviar**: materializa 1 agenda/`client_id` con flag.
- `agenda_sender`: path dual (clásico vs dispatch estrategia).
- UI: filtro agendas (default oculta Motor B); programación estrategia con defaults + preview calendario.

**Fuera de alcance F2**

- Edición manual masiva de slots en calendario.
- Auto-regenerar agendas al re-enriquecer memoria.
- Calendario visual de envíos tipo Google Calendar → **SPEC-031**.

## 4) Orden de implementación

1. Spec + shape/documentación.  
2. Backend extractores + tests (F1).  
3. Agent deprecación HSM preferred.  
4. Backoffice wizard + proxies.  
5. Migración `estrategia_id` + stage when-to-send + agenda_sender dual (F2).  
6. UI filtro agendas + schedule calendario.

**Merge:** backend (migración) → agent → backoffice → platform docs.

## 5) Migración de base de datos

### F1

Sin migración nueva: reutiliza `clients.metadata` (sql/93).

### F2

- Archivo: `backend-supabase/sql/94_agenda_estrategia_id.sql`.
- Columnas en `{schema}.agenda`:
  - `estrategia_id INTEGER NULL REFERENCES {schema}.estrategias(id) ON DELETE SET NULL`
  - `origen TEXT NULL` (`estrategia` | `manual` | `agente`)
- Índice: `(estrategia_id) WHERE estrategia_id IS NOT NULL`.
- Seed/backfill: no.
- Rollback: `DROP COLUMN estrategia_id, origen`.

## 6) Plan de prueba en CI/CD

- Backend: `tests/test_client_memory.py` (franjas, buckets, place_types, merge).
- Backend: tests stage when-to-send / filtro agenda si aplica.
- Agent: tests `upsert_preference` escribe metadata sin crear agenda ni exigir plantilla.
- Checks existentes de mapa / agendas clásicas deben seguir verdes.
- Gap: Places live sin E2E automatizado → smoke manual.

## 7) Plan de prueba humana (antes del PR)

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

**Checklist F1**

1. Mapa → zona → wizard memoria → config → pasos 1–4 con resumen → cierre checklist.
2. 1:1 desde panel/perfil → mismo wizard.
3. Verificar `metadata.preferred_contact` / `purchase_frequency` / `nearby` / `top_products` en BD.
4. Conversación agente: preferencia horaria → metadata actualizada, **sin** nueva agenda HSM preferred.

**Checklist F2**

1. Crear/editar estrategia → programación con frecuencia default + preview calendario.
2. Materializar agendas 1:1 → filas con `estrategia_id`.
3. Sección agendas general: no muestra Motor B por defecto; filtro las muestra.
4. Agenda grupo clásica sigue enviando por path HSM directo.

## 8) Shape `clients.metadata`

```json
{
  "preferred_contact": {
    "franja": "siesta",
    "hora": "14:00",
    "source": "hsm_reply|pdv_messages|generic|agent",
    "confidence": "alta|media|baja",
    "sample_size": 12,
    "ask_agent": false,
    "updated_at": "ISO"
  },
  "purchase_frequency": {
    "bucket": "1_semana|2_semanas|1_mes|otro",
    "median_days": 14,
    "confidence": "alta|media|baja",
    "sample_orders": 3,
    "updated_at": "ISO"
  },
  "nearby": { "...SPEC-028..." },
  "top_products": {
    "window_days": 90,
    "items": [{ "product_id": null, "product_code": "X", "nombre": "...", "qty": 10 }],
    "updated_at": "ISO"
  }
}
```

## 9) Dos motores de agenda

| Motor | Discriminador | Envío | UI agendas general |
|-------|---------------|-------|--------------------|
| A — Clásico | `estrategia_id IS NULL` | `agenda_sender` → HSM de la agenda | Visible por defecto |
| B — Estrategias | `estrategia_id NOT NULL` | cron → dispatch estrategia (qué decir) | Oculto; filtro / detalle estrategia |

## 10) Criterios de aceptación

### F1

- [x] Endpoints por paso persisten claves de metadata.
- [x] Wizard zona y 1:1 con resumen post-paso.
- [x] `place_types` configurable; default tipos v1.1.
- [x] `upsert_preference` no crea agenda ni exige preferred_contact plantilla.
- [x] Plantilla preferred_contact marcada deprecated en BO.

### F2

- [x] Agendas 1:1 con `estrategia_id` materializadas desde memoria + defaults.
- [x] Path dual en `agenda_sender`.
- [x] Filtro UI agendas.
- [x] Preview lista de slots en programación de estrategia (calendario visual → SPEC-031).
