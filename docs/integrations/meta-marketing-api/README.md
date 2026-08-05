# Meta Marketing API — referencia Suplai

Documentación de trabajo para el módulo Marketing (Click-to-WhatsApp). Graph API version usada en código: **v26.0**.

## Fuentes oficiales

| Tema | URL |
|------|-----|
| Marketing API overview | https://developers.facebook.com/documentation/ads-commerce/marketing-api |
| Ads that Click to WhatsApp | https://developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/messaging-ads/click-to-whatsapp |

## Archivos locales

| Archivo | Contenido |
|---------|-----------|
| [overview.md](./overview.md) | Estructura Campaign → Ad Set → Ad / Creative, permisos |
| [click-to-whatsapp.md](./click-to-whatsapp.md) | Flujo CTWA usado por Suplai (publish) |

## Credenciales por tenant

En `public.tenant_secrets` (encriptados, mismo mecanismo que WhatsApp):

| Secret | Uso |
|--------|-----|
| `meta_ads.ad_account_id` | ID de Ad Account (sin prefijo `act_` o con; el cliente normaliza) |
| `meta_ads.page_id` | Facebook Page con WhatsApp vinculado |
| `meta_ads.access_token` | Page access token con `ads_management`, `pages_manage_ads`, `pages_read_engagement`, `pages_show_list` |

## Futuro (no v1)

Motor de reglas / auto-mutación de parámetros de campaña (misma lógica conceptual que re-targeting). Ver stub en [future-rules-engine.md](./future-rules-engine.md).
