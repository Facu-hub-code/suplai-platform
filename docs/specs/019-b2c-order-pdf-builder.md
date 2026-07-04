# B2C Order PDF Builder — layout configurable del ticket de pedido cerrado

**Estado:** Aprobado (diseño)
**Fecha:** 2026-06-30
**Índice padre:** [018 B2C Post-confirm](./018-b2c-post-confirm-fulfillment.md)
**Tenant piloto:** `al_fuego`

Spec **transversal** backend + backoffice. Complementa el generador fijo actual (`order_confirmation_pdf.py`, spec backend **021**).

---

## 1) Contexto

Al cerrar un pedido B2C en `confirmado`, el cliente recibe un **link de descarga** al ticket PDF. Al Fuego (y futuros tenants B2C) necesitan:

- Logo / colores de marca
- Campos opcionales (alias de pago, instrucciones retiro, horario sucursal)
- Columnas de ítems adaptadas (mostrar **kg** en pesables, ocultar código ERP, etc.)

Hoy el PDF es código fijo Helvetica. Este spec introduce **plantillas configurables** editables desde backoffice sin deploy.

---

## 2) Objetivo

| Objetivo | Métrica |
|----------|---------|
| Operador diseña PDF sin dev | ≥1 plantilla guardada por tenant en BO |
| Link firmado temporal | URL expira (ej. 7 días); no auth cliente |
| Reutilizable | Misma plantilla para B2C confirmado; extensible a B2B email V2 |

---

## 3) Decisiones cerradas

| # | Tema | Decisión |
|---|------|----------|
| 1 | Persistencia | `public.distribuidoras.reglas_negocio.order_pdf_templates` (JSONB map) + `default_template_id` |
| 2 | Motor render | Backend fpdf2 (existente) interpreta **schema JSON** de bloques |
| 3 | V1 bloques | `header`, `order_meta`, `items_table`, `totals`, `footer`, `payment_hints`, `fulfillment_block` |
| 4 | Colores | Paleta primaria/secundaria hex en plantilla |
| 5 | Logo | URL Supabase Storage o URL pública tenant (`brand_logo_url` existente) |
| 6 | Campos ítems | Config: mostrar `product_code`, `cantidad`, `precio_unitario`, `subtotal`; label cantidad pesables = `"Kg"` |
| 7 | Link descarga | `GET /{schema}/pedidos/{id}/pdf?token=...` — JWT/HMAC con `order_id`, `exp` |
| 8 | WhatsApp | Solo URL en variable plantilla Meta; no adjunto binario V1 |
| 9 | UI | Modal **“Administrar PDF”** en sección Pedidos (backoffice spec **055**) |

---

## 4) Schema plantilla (referencia)

```json
{
  "id": "alfuego-default",
  "label": "Ticket Al Fuego B2C",
  "page": { "size": "A4", "margin_mm": 15 },
  "branding": {
    "primary_color": "#8B1A1A",
    "secondary_color": "#1A1A1A",
    "logo_url": "https://..."
  },
  "blocks": [
    { "type": "header", "title": "Resumen de tu pedido", "show_brand_name": true },
    { "type": "order_meta", "fields": ["id", "fecha", "cliente_nombre", "estado"] },
    {
      "type": "items_table",
      "columns": ["nombre", "cantidad", "precio_unitario", "subtotal"],
      "cantidad_label_pesable": "Kg",
      "cantidad_label_default": "Cant."
    },
    { "type": "totals", "show_subtotal": false, "show_total": true },
    {
      "type": "payment_hints",
      "show_alias": true,
      "show_cbu": false,
      "custom_text": "Transferí el total indicado. Alias: {{alias}}"
    },
    {
      "type": "fulfillment_block",
      "show_from_notas": true,
      "pickup_label": "Retiro programado",
      "delivery_label": "Envío a domicilio"
    },
    { "type": "footer", "text": "Gracias por elegir Al Fuego." }
  ]
}
```

Variables `{{alias}}` resuelven desde `reglas_negocio.b2c_post_confirm.payment_hints`.

---

## 5) Specs hijas

| Repo | Archivo | Contenido |
|------|---------|-----------|
| `backend/` | [061-b2c-order-pdf-builder-api.md](../../../backend-supabase/docs/specs/061-b2c-order-pdf-builder-api.md) | Validación schema, render, token URL, tests |
| `backoffice/` | [055-b2c-order-pdf-builder-ui.md](../../../product-management-app/doc/specs/055-b2c-order-pdf-builder-ui.md) | Modal Administrar PDF, preview, colores |

---

## 6) Fuera de alcance V1

- Editor WYSIWYG drag-drop
- Firma digital / QR AFIP
- Multi-idioma por plantilla
- PDF adjunto en email automático B2C (solo link WA V1)

---

## 7) Criterios de aceptación (cross-repo)

- **AC-PDF-1:** Operador guarda plantilla con color primario distinto → preview BO refleja cambio.
- **AC-PDF-2:** Pedido `confirmado` B2C genera URL válida 7 días; segunda descarga idempotente mismo PDF snapshot.
- **AC-PDF-3:** Ítem pesable muestra cantidad con label `"Kg"` según config.
- **AC-PDF-4:** Bloque `payment_hints` muestra alias configurado sin link de pago.
