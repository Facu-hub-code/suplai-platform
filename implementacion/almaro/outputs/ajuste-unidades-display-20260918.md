# Almaro — packing unidad/bulto vs display (2026-09-18)

**Tenant:** `almaro`  
**Trigger:** cliente `5493585098671` — “Dame 1 display de Rocklets” sobre Mini Bolsa `11658`.

## Qué se corrigió

El SKU `11658` ya tenía `umv_tipo=unidad` y `unidades_por_bulto=32`. El agente igual hablaba de display porque:

1. `create_order` no listaba `display` como unidad válida, entonces el modelo improvisaba.
2. `edit_order` traducía `display → umv` siempre.
3. `search_products` no trae packing; no se llamaba `get_product_by_code`.

Cambio (sin rama): `public.distribuidoras` (contexto + tool overrides) y descripción de `almaro.productos` `11658`.

## Cómo re-probar

Mismo WhatsApp: “Dame 1 display de Rocklets Mini Bolsa” → debe decir que se pide por **unidad** (bolsa) o **bulto x32**, no “no tengo la información”.
“Dame 1 display de Rocklets” genérico → preferir un SKU `umv_tipo=display` (ej. `1009` Chico).
