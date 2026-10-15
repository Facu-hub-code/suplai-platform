# 124 — Backoffice: el ERP queda en un tablero de estado

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `product-management-app` (la pestaña), `backend-supabase` (los proxies de escritura que solo usa esa pestaña)  
**Rama sugerida:** `feat/erp-tablero-estado` en backoffice, después de que el conector del [117](./117-mcp-canal-erp-o-carga.md) pueda leer y cargar  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [003](../../../product-management-app/doc/specs/003-integraciones-erp.md) en el backoffice

---

## Objetivo

En el backoffice, Integraciones ERP deja de ser un taller. Queda un tablero que dice si la conexión está viva, cuándo corrió el último sync y cuántas filas hay en cada espejo. Las acciones que hoy se hacen ahí —traer, vincular, promover, proyectar, prender el push— salen de la pantalla. Eso pasa al conector MCP y al job que ya corre solo.

### Criterios de aceptación

- La pestaña muestra conector, frecuencia, último sync, último error y los conteos de listas, productos, precios, clientes y pedidos.
- No hay botón de actualizar desde el ERP, ni de alta, ni de vínculo, ni de proyección, ni el interruptor de push.
- El job de precios y stock, y el resto de las bajadas del [117](./117-mcp-canal-erp-o-carga.md), siguen corriendo igual.
- Un tenant sin config ve “sin ERP conectado” y no ve un formulario para cargarlo.

---

## Qué se ve hoy

`ErpIntegrationsSection`, dentro de Configuración. Arriba, la card de conexión (logo, estado, diálogo Conectar, interruptor de push). Después, `ErpDependencyHealthPanel`. Después los pasos operativos: listas crudas, productos crudos con “Actualizar desde ERP” y alta de SKU, sync de precios, clientes crudos y cola, pedidos crudos y proyección.

El tablero de salud ya existe. El resto son acciones.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Qué queda | Una sola card de estado, armada con `GET /erp/config` y `GET /erp/dependency-health` | Esos dos reads ya dicen si hay conector, la capability, el último sync y los pendientes. No hace falta otra API | Rehacer el panel con un endpoint nuevo |
| Acciones | Salen de la pestaña. No se esconden detrás de un permiso | El supervisor concilia por el conector. Dos lugares para la misma alta se pisan | Dejar los botones “por si el MCP falla” |
| Conectar y editar credenciales | Salen de esta pantalla | Cargar URL y secretos es una acción. El tablero solo muestra si ya hay config | Dejar el diálogo Conectar como única excepción |
| Push | Se muestra como texto (prendido o apagado). El switch se va | Prenderlo desde la UI manda pedidos al ERP. El job ya lee `push_orders_enabled` | Seguir el interruptor en la card de estado |
| Job | No se toca | Precio y stock siguen con `sync_frequency`. El resto sigue con la capability del perfil, como está en el [117](./117-mcp-canal-erp-o-carga.md) | Apagar el cron porque la pantalla ya no tiene “Sincronizar” |
| Endpoints de escritura | El backoffice deja de proxearlos. El backend los conserva para el job y para quien ya los llama por API | Borrar el router rompería el cron | Borrar `sync_prices_for_schema` junto con el botón |
| Badge de cliente | `erp-sync-badge` se queda en la ficha. No dispara sync | Es un estado, no una acción | Sacar también las etiquetas de las otras pantallas en esta entrega |

---

## Alcance

### Incluido

La pestaña Integraciones ERP pasa a mostrar:

- Conector y si está configurado.
- `sync_frequency`, `last_sync_at`, `last_error`.
- Push como lectura.
- Conteos del health: listas, productos, precios, clientes, pedidos (en espejo, vinculados, pendientes).

Salen de la pestaña, y sus proxies en `app/api/erp/` que solo sirven a esos botones:

- Diálogo Conectar y `POST /api/erp/connect`.
- Interruptor de push y `POST /api/erp/config/push-orders`.
- Actualizar productos, export, alta masiva, `load-products`, `promote-products-bulk`.
- Listas: cargar, vincular, desvincular, onboarding apply y dismiss.
- Sync manual de precios y `sync-prices` / `load-prices`.
- Clientes crudos, cola, aprobar, descartar, promover, link.
- Pedidos crudos, reconciliar, proyectar, `sync-orders`.
- La guía de pasos y los diálogos de esa operación.

### Fuera de alcance

- Cambiar el cron, las capabilities o `run_erp_sync_job`.
- Las tools `traer_*` y la carga del conector. Ya están en el [117](./117-mcp-canal-erp-o-carga.md) y el [116](./116-mcp-pedidos-crud.md).
- Borrar routers de escritura del backend.
- Quitar el badge de ERP en la ficha del cliente o en la tabla de productos.
- Un formulario nuevo para dar de alta la conexión.

---

## Orden de implementación

| Orden | Repo | Qué |
|---|---|---|
| 1 | backoffice | La pestaña queda en el tablero. Se dejan de renderizar las secciones de acción |
| 2 | backoffice | Se borran los proxies que ya nadie llama desde la UI |
| 3 | — | El backend no cambia en este PR |

Si el [117](./117-mcp-canal-erp-o-carga.md) todavía no está en el entorno donde opera el supervisor, este PR no se mergea antes. Si no, la pantalla pierde las acciones y el chat todavía no las reemplaza.

---

## Migración de base de datos

Sin migración. No se borra config, ni espejo, ni capabilities.

---

## Plan de prueba en CI/CD

En `product-management-app`:

- Un render de la pestaña con config no muestra los textos “Actualizar desde ERP”, “Conectar”, ni el switch de push.
- Con config vacía muestra “sin ERP conectado” y no muestra el formulario.
- El typecheck sigue verde.

No hay test nuevo de backend. El job no se modifica.

---

## Plan de prueba humana

Backoffice en `http://localhost:3000`, backend en `8000`. Tenant `gonzales`.

1. Abrir Configuración → Integraciones ERP.
2. Ver conector GEV, frecuencia 6 horas, último sync y los conteos. No hay pasos de productos, listas, clientes ni pedidos.
3. Recargar a los pocos minutos. Los números pueden cambiar solos si el job corrió. La pantalla no tiene un botón para forzarlo.
4. Entrar con un tenant sin fila en `erp_connector_configs`. La pestaña dice que no hay ERP y no ofrece conectar.
5. En productos o en la ficha de un cliente, el badge de ERP sigue visible.
