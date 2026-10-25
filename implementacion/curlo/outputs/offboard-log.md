# Offboard — CURLO

- Schema: `curlo`
- Tenant: `e67ea0ca-ce05-4608-884d-227440e3f5db`
- Fecha: 2026-10-24
- Motivo: baja pedida por el cliente. Borrado de sus datos.
- Rama git: no se abrió ninguna. Checkout actual del hub: `docs/gev-promos-cabecera`. Sin commit.

## Producción (verificado después del borrado)

| Recurso | Después |
|---|---|
| Schema `curlo` | no existe |
| Fila `public.distribuidoras` | 0 |
| Profiles | 0 |
| Usuarios de acceso | 0 |
| Secretos | 0 (no había ninguno) |
| Conector ERP | 0 (no había fila) |
| Conversaciones, mensajes, copilot | 0 |
| Plantillas y seguimientos de este tenant | 0 |
| Logs de retrain | 0 |
| Proyecto de implementación | 0 |
| Archivos en storage con nombre `curlo` | 0 |
| Número de agente del tenant | liberado (ningún otro tenant lo tenía) |

Cuentas borradas, exclusivas de este tenant: `admin@curlo.com`, `curlo@suplaisales.com`.

Las plantillas con el mismo nombre en otros tenants son copias propias. No se tocaron.

## Filas que había y se eliminaron

| Dónde | Filas |
|---|---|
| `curlo.items_pedido` | 31943 |
| `curlo.productos_aliases` | 7721 |
| `curlo.pedidos` | 5762 |
| `curlo.clients` | 1664 |
| `curlo.puntos_venta` | 1664 |
| `curlo.precios_productos` | 1489 |
| `curlo.documents` (embeddings) | 929 |
| `curlo.productos` | 929 |
| `curlo.vendedores_clientes` | 565 |
| `public.sales_engine_retrain_logs` | 76 |
| `core.inbound_messages` | 14 |
| `core.agent_tool_executions` | 13 |
| `core.copilot_messages` | 10 |
| `curlo.vendedores` | 6 |
| `curlo.etiquetas` | 5 |
| `core.copilot_conversations` | 4 |
| `public.meta_plantillas` | 4 |
| `curlo.field_task_templates` | 3 |
| `curlo.listas_precios` | 3 |
| `public.followup_sequences` | 3 |
| `public.implementation_project_user_stories` | 3 |
| `auth.users` | 2 |
| `public.implementation_project_milestone_log` | 2 |
| `public.notification_subscriptions` | 2 |
| `public.profiles` | 2 |
| `curlo.grupos` | 1 |
| `public.implementation_projects` | 1 |
| `public.distribuidoras` | 1 |
| Schema `curlo` | dropeado |

## Copias locales

Se borraron del disco 50 archivos de datos: CSV de catálogo, clientes, pedidos y mensajes, el prompt exportado, y los dumps de ERP en `inputs/erp/` (gitignored, ~30 MB: clientes, domicilios, precios y pedidos).

Quedan en la carpeta los scripts, `config.json` y esta nota. No re-ejecutar los scripts: el schema ya no existe.

## Qué no se borró

- Historial de git: los CSV que ya estaban commiteados siguen en commits anteriores. No se reescribió historia ni se hizo commit. El working tree de `docs/gev-promos-cabecera` queda con esos archivos borrados, sin stagear.
- Eventos de Mixpanel, si los hubo.
- El sitio `curlomayorista.com.ar` (no es nuestro).
- Menciones del nombre `curlo` en documentación interna (por ejemplo el spec 109). No son registros de clientes.
