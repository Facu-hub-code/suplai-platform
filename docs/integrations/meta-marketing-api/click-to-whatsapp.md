# Ads that Click to WhatsApp — flujo Suplai

Fuente oficial: [Click to WhatsApp](https://developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/messaging-ads/click-to-whatsapp) (actualizado May 21, 2026).

## Prerrequisitos

- Ad Account Meta
- Assets subidos (Suplai: bucket `meta_ads_creatives` + `act_{id}/adimages` al publish)
- Facebook Page con número WhatsApp linked
- Token con `ads_management`, `pages_manage_ads`, `pages_read_engagement`, `pages_show_list`

## Paso 1 — Campaign

`POST /act_{AD_ACCOUNT_ID}/campaigns`

- `objective=OUTCOME_ENGAGEMENT` (también soporta LEADS / SALES / TRAFFIC; call prompts requieren ENGAGEMENT)
- `special_ad_categories=[]` (o categorías aplicables)
- `status=PAUSED|ACTIVE`

## Paso 2 — Ad Set

`POST /act_{AD_ACCOUNT_ID}/adsets`

Requeridos / usados en Suplai:

| Campo | Valor v1 |
|-------|----------|
| `campaign_id` | ID del paso 1 |
| `destination_type` | `WHATSAPP` |
| `billing_event` | `IMPRESSIONS` |
| `optimization_goal` | `CONVERSATIONS` |
| `promoted_object` | `{ "page_id": "<PAGE_ID>" }` (+ opcional `whatsapp_phone_number`) |
| `daily_budget` XOR `lifetime_budget` | En unidades menores de la moneda de la cuenta |
| `start_time` / `end_time` | ISO / UNIX según API |
| `targeting.geo_locations.custom_locations` | Derivado de `geo_zones` (lat, lng, radius) |
| `bid_strategy` | `LOWEST_COST_WITHOUT_CAP` (default) |

## Paso 3 — Ad Creative

`POST /act_{AD_ACCOUNT_ID}/adcreatives`

`object_story_spec`:

- `page_id`
- `link_data.message` — primary text
- `link_data.name` — headline
- `link_data.image_hash` — de adimages
- `link_data.link` — `https://api.whatsapp.com/send`
- `link_data.call_to_action.type` — `WHATSAPP_MESSAGE`
- `link_data.page_welcome_message` — estructura VISUAL_EDITOR v2 (greeting + autofill)

## Paso 4 — Ad

`POST /act_{AD_ACCOUNT_ID}/ads` con `adset_id`, `creative.creative_id`, `status`.

## Paso 5 — Publish

Activar `status=ACTIVE` en campaign/adset/ad según Ads Manager o API. Meta revisa (`PENDING_REVIEW` → `ACTIVE`).

## Atribución inbound (agente)

El primer mensaje WhatsApp por CTWA puede traer `referral` con `ctwa_clid`, `source_id`, etc. Suplai lo persiste en `core.conversation_ad_attribution` para el dashboard.
