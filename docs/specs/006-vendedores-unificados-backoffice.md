# Backoffice — Sección Vendedores unificada (Suplai Field integrado)

**Estado:** Aprobado (diseño)  
**Fecha:** 2026-06-20  
**Supersede:** navegación separada "Suplai Field" de [044](../../../product-management-app/doc/specs/044-field-app-supervisor.md)  
**Implementación backoffice:** `product-management-app/doc/specs/045-vendedores-unificados.md` (pendiente)  
**BFF backend:** `backend/docs/specs/051-bff-vendedores.md` (pendiente)

---

## 1) Objetivo

Unificar **Vendedores** y **Suplai Field** en una sola sección del backoffice. El supervisor gestiona equipo comercial, WhatsApp, tareas, torneos y progreso desde un único lugar con UX de **ficha estilo FIFA** por vendedor.

---

## 2) Feature flag

| Antes | Después |
|-------|---------|
| `sales_assistant_enabled` → sección Vendedores | **Único flag** para toda la sección |
| `metadata.field_app_enabled` → sección Suplai Field | **Deprecado** — Field es parte del módulo vendedor |

Migración:

```sql
-- Tenants con field_app_enabled pasan a sales_assistant_enabled si no lo tenían
UPDATE public.distribuidoras
SET sales_assistant_enabled = true
WHERE (metadata->>'field_app_enabled')::boolean = true;
-- metadata.field_app_enabled: dejar de leer; limpiar en job posterior
```

Sidebar: **un solo ítem "Vendedores"** (icono `UserCheck` o similar). Eliminar ítem "Suplai Field".

---

## 3) Layout de la sección

```text
┌─────────────────────────────────────────────────────────────┐
│  SECCIÓN VENDEDORES                                          │
├─────────────────────────────────────────────────────────────┤
│  [Card WhatsApp]  [Card Torneo ▼]  [Card Plantillas ▼]      │  ← fila compacta superior
├─────────────────────────────────────────────────────────────┤
│  Búsqueda · Filtro activo · Nuevo vendedor                   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Ficha    │  │ Ficha    │  │ Ficha    │  ... grid         │  ← estilo carta FIFA
│  │ vendedor │  │ vendedor │  │ vendedor │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Fila superior — 3 tarjetas

| # | Tarjeta | Contenido compacto | Expansión |
|---|---------|-------------------|-----------|
| 1 | **WhatsApp** | 3 métricas: conectados / QR pendiente / desconectados (como hoy) | Sin modal; acciones por ficha |
| 2 | **Torneo activo** | Nombre, días restantes, líder, pts líder | **Modal** con `FieldTournamentsView` completo (CRUD + cerrar + historial) |
| 3 | **Plantillas de tareas** | Count activas, tipos habilitados, pts default | **Modal** con `FieldTemplatesTable` + reglas de negocio legibles |

### 3.2 Ficha vendedor (carta FIFA)

```
┌─────────────────────────────┐
│      ┌─────────┐            │
│      │  FOTO   │  Nombre    │
│      │ avatar  │  Teléfono  │
│      └─────────┘  ● Activo  │
│  ─────────────────────────  │
│  📱 WA: Conectado           │
│  🏆 Torneo: #2 · 340 pts    │
│  ✅ Tareas hoy: 3/8 (38%)   │
│  ⭐ Pts hoy: 120/280         │
│  ─────────────────────────  │
│  [Editar] [Zonas] [Clientes]│
│  [WhatsApp] [Desactivar]    │
└─────────────────────────────┘
```

**Foto de perfil:**

- Upload desde backoffice → Supabase Storage bucket `{tenant}/vendedores/{id}.jpg`
- Columna nueva: `{schema}.vendedores.avatar_url` (public URL)
- Fallback: iniciales en avatar circular (como productos)

**Dashboard diario:** dentro de la ficha (no en la fila superior). Selector de fecha opcional en modal expandido de ficha (V1.1) o inline en card expandida al click.

---

## 4) BFF `GET /{schema}/bff/vendedores`

Patrón existente: [bff/clients](../../../backend-supabase/services/bff_clientes_service.py).

### 4.1 Request

```http
GET /{schema}/bff/vendedores?fecha=2026-06-20&activo=true&search=juan
x-schema-name: gonzales
```

### 4.2 Response (por vendedor)

```json
{
  "vendedores": [
    {
      "id": 5,
      "nombre": "Juan Pérez",
      "telefono": "54911...",
      "email": null,
      "activo": true,
      "avatar_url": "https://...supabase.co/storage/.../5.jpg",
      "zona": "Norte",
      "whatsapp": {
        "estado": "conectado",
        "instance_id": "..."
      },
      "field_hoy": {
        "fecha": "2026-06-20",
        "tareas_logradas": 3,
        "tareas_pendientes": 5,
        "tareas_parciales": 1,
        "pts_logrados": 120,
        "pts_posibles": 280,
        "pct_completitud": 43
      },
      "torneo": {
        "activo": true,
        "nombre": "Torneo Junio",
        "posicion": 2,
        "puntos": 340,
        "lider_nombre": "María",
        "lider_puntos": 410
      }
    }
  ],
  "meta": {
    "total": 12,
    "torneo_activo_id": 3,
    "whatsapp_resumen": { "conectados": 8, "pendientes_qr": 2, "desconectados": 2 }
  }
}
```

### 4.3 Proxy backoffice

`GET /api/bff/vendedores` → backend Railway.

---

## 5) Componentes (backoffice)

| Componente | Acción |
|------------|--------|
| `VendedoresTable` | **Reemplazar** por `VendedoresGrid` + `VendedorFichaCard` |
| `FieldShell` | **Eliminar** como sección; migrar tabs a modales |
| `FieldDashboardView` | Integrar métricas en ficha; tabla detalle opcional en modal |
| `FieldTemplatesTable` | Modal "Plantillas" |
| `FieldTournamentsView` | Modal "Torneo" |
| Nuevo `VendedorAvatarUpload` | Upload a Supabase vía API |

---

## 6) Configuración Field (inline)

Mover settings de Field al modal Plantillas o panel lateral:

- Ventana combo (días)
- Delta unidades
- Max items combo
- Puntos por SKU / bonus default

Persistir en `distribuidoras.metadata.field_config` o tabla dedicada.

---

## 7) Criterios de aceptación

- [ ] Un solo ítem sidebar "Vendedores"; no existe "Suplai Field" separado.
- [ ] Grid de fichas con foto, WA, torneo y progreso del día.
- [ ] 3 tarjetas superiores; torneo y plantillas abren modal.
- [ ] BFF agrega en una sola llamada lo que hoy requiere 3+ endpoints.
- [ ] Upload avatar genera public URL en Supabase Storage.
- [ ] `field_app_enabled` deja de leerse; login Field valida `sales_assistant_enabled`.
