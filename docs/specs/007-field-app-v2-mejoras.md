# Suplai Field App — Mejoras V2 (diseño)

**Estado:** Aprobado (diseño)  
**Fecha:** 2026-06-20  
**Repo:** `field-app/`  
**Implementación:** `field-app/docs/specs/002-field-app-v2-mejoras.md` (pendiente)

---

## 1) Respuestas a preguntas de producto (estado actual vs propuesto)

### 1.1 Logout y perfil de usuario

| Pregunta | Estado actual | Decisión V2 |
|----------|---------------|-------------|
| ¿Logout implementado? | **No.** Existe `clearSession()` en `lib/field-session.ts` pero no hay UI que lo invoque. | Agregar pantalla **Perfil** accesible desde header o reemplazar un tab |
| ¿Perfil implementado? | **No.** Spec 001 menciona `config/page.tsx` pero **no existe** en el repo. BottomNav solo tiene: Mi Día, PDV, Pedidos, Torneo. | Implementar `/{schema}/perfil` |

**Contenido pantalla Perfil:**

- Foto (desde `avatar_url` del BFF vendedor, fallback iniciales)
- Nombre, teléfono, zonas asignadas
- Distribuidora + logo
- Versión de la app
- Botón **Cerrar sesión** → `clearSession(schema)` + redirect a login

**Opción UX:** icono de usuario en `FieldHeader` en lugar de quinto tab en BottomNav (mantener 4 tabs).

---

### 1.2 CI/CD

| Capa | Estado actual |
|------|---------------|
| **CI** | ✅ Implementado — `.github/workflows/ci.yml`: `npm ci` → `npm test` → `npm run build` en push/PR a `main` |
| **CD** | ⚠️ Implícito vía **Vercel ↔ GitHub** (no hay workflow `deploy.yml` en repo). Deploy automático al mergear en `main` si el proyecto Vercel está vinculado. |

**Acción V2 (opcional):** documentar en README el link Vercel + env vars (`BACKEND_URL`). Agregar workflow de preview comment en PR si se desea visibilidad explícita.

---

### 1.3 Icono "?" — criterio de PDV en Home y sección PDV

**No implementado hoy.** Agregar en V2:

| Ubicación | Icono `HelpCircle` | Contenido tooltip/modal |
|-----------|-------------------|-------------------------|
| Home — "Ruta de Hoy" | Sí | Explicación de criterio de ruta (ver §2) |
| PDV — listado cartera | Sí | Diferencia ruta vs cartera completa + filtros |

Texto sugerido (español rioplatense, editable):

> **¿Por qué veo estos PDV?**  
> En *Mi Día* aparecen los puntos de venta de tu ruta de **hoy**: zonas geo asignadas a vos con día de visita = hoy, más tus clientes con día de visita directo si el tenant no usa zonas.  
> Si falta un cliente, revisá en el backoffice: asignación vendedor ↔ zona, `dia_visita` de la zona, o `dia_de_visita` del cliente.

---

### 1.4 Fallback de la vista PDV — comportamiento real (documentado)

Basado en `FieldTaskService.fetch_route_pdvs` y `VendedorAppService`:

#### Home — "Ruta de Hoy"

```text
1. PRIMARIO (spec 040 — tenant con geo-zonas):
   puntos_venta
   JOIN geo_zones ON pv.geo_zone_id = gz.id
   JOIN vendedor_geo_zones ON vgz.geo_zone_id = gz.id
   WHERE vgz.vendedor_id = yo
     AND gz.dia_visita = DIA_HOY
     AND pv.vendedor_id = yo

2. FALLBACK (tenant legacy sin match primario):
   vendedores_clientes
   JOIN clients ON c.id = vc.cliente_id
   WHERE vc.vendedor_id = yo
     AND c.dia_de_visita = DIA_HOY
```

**Importante:** Home muestra **solo la ruta del día**, no toda la cartera.

#### Sección PDV (tab "PDV")

`GET /vendedor-app/pdv` → **toda la cartera** asignada via `vendedores_clientes`, con filtros opcionales (`search`, `dia_de_visita`, `categoria`). Sin filtro de día = todos los clientes del vendedor.

El icono "?" debe dejar esto explícito (ver §1.3).

---

### 1.5 Caso "Coca Cola" — frecuencia 2 visitas/semana

**Estado del modelo (spec 040):** una `geo_zone` = **un solo** `dia_visita`. No existe campo `frecuencia` ni multi-día en una zona.

**Decisión recomendada (mantener spec 040):**

> **Dos geo-zonas** para la misma área geográfica visitada 2 veces por semana.

Ejemplo Coca Cola:

| Geo-zona | dia_visita | Polígono |
|----------|------------|----------|
| Zona Norte — Lunes | lunes | Mismo polígono (copiado) |
| Zona Norte — Jueves | jueves | Mismo polígono |

Ventajas:

- Compatible con motor de ruta actual (`gz.dia_visita = hoy`).
- Sin migración de schema.
- Backoffice ya modela M:N vendedor ↔ zonas.

**No recomendado V2:** agregar `dias_visita[]` a geo_zones — rompe spec 040 y complica mapa/filtros.

Documentar en tooltip "?" y en guía de onboarding territorio.

---

### 1.6 ¿Cuándo se crean las tareas?

**Estado actual:** lazy — `FieldTaskService.ensure_daily_tasks()` se ejecuta en **`GET /vendedor-app/home`** (primer acceso del vendedor al día). Idempotente por `(vendedor_id, cliente_id, tipo, fecha)`. **No hay CRON** implementado.

**Recomendación V2 — híbrido:**

| Mecanismo | Cuándo | Propósito |
|-----------|--------|-----------|
| **CRON nocturno** | ~05:30 TZ tenant (`FIELD_APP_TZ`) | Pre-generar tareas del día para todos los vendedores activos; evita cold start lento en primer home |
| **Lazy on home** | Primer `GET /home` del vendedor | Captura PDVs nuevos en ruta, plantillas activadas después del CRON, cambios de asignación intra-día |
| **Sync ERP** | Post-sync | **Re-evalúa** cumplimiento de tareas existentes; **no regenera** combos |

**No regenerar combos** si el vendedor hace refresh — los SKUs sugeridos quedan fijos para el día (evita confusión).

Config backoffice: `field_generacion_modo: 'cron_y_lazy' | 'solo_lazy'` (default híbrido).

---

### 1.7 Pedidos desde ficha PDV (sugerencia aceptada)

**Estado actual:**

- Home → card PDV → tap → **ficha** `pdv/[id]` con KPIs, tareas, top productos.
- Tab **Pedidos** global — lista todos los pedidos del vendedor, sin navegación desde avatar PDV.
- No hay sección "pedidos históricos" en ficha PDV.

**Diseño V2 — flujo propuesto:**

```text
Home (ruta) → Card PDV (resumen + tareas)
           → Perfil PDV completo (ficha FIFA comercial)
                ├── KPIs + tendencia
                ├── Tareas activas (SKUs sugeridos)
                ├── Top productos
                └── Pedidos históricos (N últimos confirmados)
                     └── tap → detalle pedido (solo lectura V2)
```

**Acceso rápido:** tap en **avatar del PDV** en Home → ficha completa (ya parcialmente implementado). Agregar sección pedidos:

```http
GET /{schema}/vendedor-app/pdv/{id}/pedidos?page=1&page_size=10
```

Mostrar: fecha, estado, total, ítems count. Link "Ver todos" → tab Pedidos filtrado por cliente.

---

## 2) Navegación actualizada (propuesta)

```text
BottomNav: Mi Día | PDV | Pedidos | Torneo
Header: [?] ayuda contextual · [avatar vendedor] → Perfil
```

---

## 3) Cambios de API requeridos (field-app)

| Endpoint | Uso |
|----------|-----|
| `GET /vendedor-app/pdv/{id}/pedidos` | Histórico en ficha PDV |
| `GET /vendedor-app/me` o extensión login | Perfil vendedor + avatar_url |
| Home/tareas | Incluir `combo_skus`, progreso parcial, badge confianza frecuencia |

---

## 4) Criterios de aceptación V2

- [ ] Pantalla perfil con logout funcional.
- [ ] Icono "?" en Home y PDV con copy de criterios de ruta/cartera.
- [ ] Ficha PDV incluye pedidos históricos.
- [ ] Tareas muestran SKUs sugeridos y progreso (cuando exista).
- [ ] Documentación onboarding explica caso 2 visitas/semana = 2 geo-zonas.
- [ ] CRON nocturno documentado e implementado en backend (spec 050).
