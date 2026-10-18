# 116 — Carga de pedidos del ERP (con API y sin API)

**Estado:** Borrador. Escritura compartida. No incluye el alta ni la edición de un pedido operativo de Suplai.  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase`  
**Rama sugerida:** `feat/mcp-carga-pedidos` desde `origin/main`, después de la lectura del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [095](./095-claude-mcp-carga-clientes-productos.md), regla `.cursor/rules/backend-capas.mdc`  
**No tocar:** `mcp_server/esquema_publico.py`, `tests/test_mcp_esquema_gemini.py`, salvo que el catálogo se arme al registrar las tools. No reescribir `consultar_pedidos`.

---

## Objetivo

Una sola tool persiste los pedidos del ERP que todavía no están en Suplai, y da de baja los que esta misma carga había guardado y ya no vienen en la fuente.

Sin API, Claude lee el Excel y arma el lote. Con API, los pedidos entran por el job y la proyección, y Claude los ve con `consultar_pedidos` (`origen=erp`). Esta tool no es el camino de las métricas.

### Criterios de aceptación

- Un lote de hasta 5000 filas marca cada una por dentro. Claude recibe los conteos, los `faltantes` y hasta 100 motivos de rechazo. Las aceptadas quedan en el preview del server.
- Confirmar dos veces el mismo `preview_id` no inserta de nuevo.
- `accion: baja` solo borra filas de `pedidos_externos` de ese schema. No borra un pedido `origen` suplai, tienda o erp.
- La tool no llama `sync_orders_to_raw` ni `tienda_confirm_pedido_core`.
- Sirve en `del_corro`, donde no hay API. En un tenant con API el histórico no se carga por esta tool: lo escribe la proyección.

---

## Capas

| Capa | Dónde | Hace |
|---|---|---|
| MCP | `mcp_server/pedidos_carga_tools.py` y un `tipo` en `confirmar_dispatch` | Scope `pedidos:escribir`, preview, auditoría |
| Adaptador | `services/mcp_pedidos_carga.py` | Guarda el preview en `mcp_accion_previews`. Llama al dominio con las filas aceptadas |
| Dominio | `services/pedidos_externos_service.py` | Acepta, rechaza, ya existe, alta, baja |
| Datos | `data_access/pedidos_externos.py` | INSERT y DELETE de `pedidos_externos` |

El adaptador no importa `routers` ni un conector ERP. No copia `services/mcp_carga.py`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Una tool | `previsualizar_carga_pedidos` + `confirmar` con tipo `carga_pedidos_externos` | El insert es el mismo si la fila salió de un Excel o de un `sale.order` | Una tool de carga por conector |
| Alta | Insert en `{schema}.pedidos_externos` de las filas `aceptada` | Es el comprobante histórico. No es un carrito | Insertar en `pedidos` o llamar `tienda_confirm_pedido_core` |
| Baja | `accion: baja` con `numero_comprobante`. Solo si la fila está en `pedidos_externos` | El Excel nuevo puede no traer un comprobante que se cargó antes | Borrar `pedidos` de la tienda o de Field |
| Ya existe | Mismo comprobante en el lote, en `pedidos_externos`, o en `pedidos.erp_reference_id` | La proyección vieja del ERP ya pudo ocupar ese número | Insertar igual |
| Código | `clients.codigo` es `numeric` en los 40 schemas. Se compara numérico | `"0012"` y `12` son el mismo código | Tratarlo como texto libre |
| Formato | `fecha`, `codigo` o `erp_partner_id`, `total`, `numero_comprobante`. Renglones con `product_code` y `cantidad` cuando el comprobante los trae. Opcionales: `estado`, `canal` | El cliente y cada producto se validan por identificador. Sin API, Claude lo arma desde el Excel | Pedirle al conector que escriba esta tabla |
| Coincidencia | El cliente resuelve a `clients` (`codigo` numérico o `partner_erp_id`). Cada `product_code` existe en `productos.product_code`. Si no, la fila se rechaza y `faltantes` lista esos ids | Claude puede pedir el detalle en el ERP y cargar el cliente o el producto antes de repetir el pedido. El confirmar de pedidos no los crea | Aceptar la fila y dejar el renglón colgado, o insertar el producto dentro del mismo confirmar |
| Tope | 5000 filas por preview. La respuesta al chat no repite las aceptadas: conteos, `faltantes` y hasta 100 motivos | Diez mil pedidos en tandas de 100 son cien idas al MCP. La fila de cabecera es chica. Lo pesado es devolverle a Claude cada aceptada | Dejar el tope en 100, o devolver las 5000 filas aceptadas en el chat |
| Scope | `pedidos:escribir`, fuera del bypass `CONECTOR_ACEPTA_TOOLS_NUEVAS` | Cargar comprobantes es otro consentimiento que leer | Darlo por concedido a quien ya tiene `pedidos:leer` |
| Match con un pedido Suplai | Fuera de esta entrega | La etapa es alta y baja del comprobante externo | Vincular por tolerancia de monto en el mismo confirmar |

---

## Alcance

### Incluido

- Preview y confirmar de alta.
- Preview y confirmar de baja, limitada a `pedidos_externos`.
- Rechazos: falta fecha, identificador de cliente, total o comprobante; el cliente no coincide con `clients`; un renglón cuyo `product_code` no está en `productos`; total que no es un número `>= 0`; comprobante repetido o ya cargado; fecha ilegible; baja de un comprobante que no está en `pedidos_externos`. Si falla un renglón, se rechaza el pedido entero. La respuesta incluye `faltantes.clientes` y `faltantes.productos`.

### Fuera de alcance

- Crear, editar o confirmar un pedido `abierto` de Suplai.
- Bajar pedidos del ERP por MCP. Con API los escribe el job ([117](./117-mcp-canal-erp-o-carga.md)).
- Push al ERP y `sync_orders_to_raw`.
- Borrar un pedido de tienda, Field o del agente.

---

## Orden de implementación

Un PR en `backend-supabase`: migración, `data_access`, dominio, adaptador, tool. No depende de una tool de lectura de pedidos.

---

## Migración de base de datos

SQL nuevo, número libre. Tabla por cada schema de `public.distribuidoras`, incluido el de `choose_template_schema`.

```text
{schema}.pedidos_externos
  id
  numero_comprobante text NOT NULL UNIQUE
  fecha date NOT NULL
  cliente_id int NOT NULL
  codigo numeric NOT NULL
  total numeric NOT NULL
  estado text NULL
  canal text NULL
  items jsonb NOT NULL DEFAULT '[]'
  created_at timestamptz NOT NULL DEFAULT now()
```

Sin FK a `pedidos`. No altera `clients` ni las vistas `v_cartera` / `v_prospectos`.

Check de `mcp_accion_previews.tipo`: sumar `carga_pedidos_externos`, igual que `sql/163`.

Rollback: sacar el tipo del check y `DROP TABLE` por schema. No hay backfill.

---

## Plan de prueba en CI/CD

Pytest de servicio, sin MCP real:

- Lote con fila aceptada, código inexistente, comprobante duplicado y total inválido.
- Segundo confirmar del mismo preview no inserta.
- Baja de un comprobante cargado lo saca. Baja de un `pedidos.id` de origen tienda no lo toca.
- `erp_reference_id` ya presente queda `ya_existe`.
- Un pedido con cliente inexistente, o con un `product_code` que no está en `productos`, queda `rechazada` y no se inserta. El resto del lote sigue.
- No llama `sync_orders_to_raw` ni `tienda_confirm_pedido_core`.
- `scope_alcanza(["pedidos:leer"], "pedidos:escribir")` es falso.

---

## Plan de prueba humana

La corrida por tenant está en el sub-spec de cada ERP. En todas: previsualizar, no confirmar hasta ver el preview, confirmar una sola fila de prueba, confirmar otra vez y ver que no duplica. En `del_corro` la fuente es un Excel de 3 filas (una con código malo). En un tenant con API, los pedidos de métricas se miran con `consultar_pedidos`, no se cargan por esta tool.
