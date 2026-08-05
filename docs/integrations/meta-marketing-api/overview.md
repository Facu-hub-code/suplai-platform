# Marketing API — overview (notas Suplai)

Fuente: [Marketing API](https://developers.facebook.com/documentation/ads-commerce/marketing-api) (Meta, Ads and Commerce).

## Estructura de objetos

1. **Campaign** — objetivo (`OUTCOME_ENGAGEMENT` para CTWA v1 Suplai).
2. **Ad Set** — presupuesto, schedule, targeting, `destination_type`, `promoted_object`, optimization.
3. **Ad Creative** — assets + copy + CTA + `page_welcome_message` (WhatsApp).
4. **Ad** — une creative + ad set; status ACTIVE/PAUSED.

## APIs relacionadas (fuera de v1 Suplai)

- Conversions API
- Catalog API
- Business Management API
- Commerce API

## Insights

Lectura típica: `GET /{ad_set_id}/insights` con fields `impressions`, `clicks`, `spend`, `actions` (tipos messaging / conversaciones CTWA).

Version Graph en código Suplai: `v26.0`.
