# Offboard log — distribuidora_saffadi

- Schema origen: `distribuidora_saffadi`
- Destino WhatsApp: `kiki_market`
- Autorización: implementación del plan aprobado + frase `ELIMINAR TENANT distribuidora_saffadi`

## Pre (2026-09-30)

| Recurso | Valor |
|---|---|
| Saffadi activa | true |
| Saffadi phone | 5493582430647 |
| Kiki phone | 5493541607139 |
| Secretos Saffadi | 5 whatsapp.* |
| Secretos Kiki | 0 |
| Plantillas Saffadi | 7 |
| Productos Kiki | 510 |
| Schema Saffadi | existe (78 tablas) |

## Post (2026-09-30)

| Recurso | Valor |
|---|---|
| Schema `distribuidora_saffadi` | no existe |
| Fila `public.distribuidoras` Saffadi | 0 |
| Secretos Saffadi | 0 |
| Plantillas Saffadi | 0 |
| Profiles Saffadi | 0 |
| Conversaciones core Saffadi | 0 |
| Auth users Saffadi | 0 |
| Kiki activa | true |
| Kiki phone | 5493582430647 |
| Secretos Kiki | 5 whatsapp.* |
| Plantillas Kiki | 7 |
| Productos Kiki | 510 |
| Owner Kiki | Admin Kiki Market (role=owner) |
| Followups Kiki | 2 (sin tocar) |

## Fuera de alcance (queda huérfano)

- Webhook ERP Railway: `https://primary-production-c1d08.up.railway.app/webhook/pedidos_saffadi`
