# Benfresh — Caso de uso real: central de pedidos vendedor

## Situación actual (AS-IS)

- Los vendedores de campo reciben pedidos de sus clientes (PdV) por WhatsApp.
- Reenvían esos mensajes (texto, fotos de listas, audios) a un **teléfono central** de la distribuidora.
- Una persona del back office **carga el pedido a mano** en Odoo/ERP.

## Objetivo (TO-BE)

Automatizar la carga usando el **agente asistente de vendedor**:

1. El operador (o el mismo vendedor con perfil seller) recibe el reenvío en el WhatsApp del agente.
2. Identifica al **cliente** (`set_seller_selected_client` / `get_seller_client_details`).
3. Interpreta el contenido:
   - **Texto libre** con cantidades y productos → `resolve_free_text_order`
   - **Foto de lista** (manuscrita o captura) → visión + `resolve_free_text_order` o búsqueda + `create_order_for_client`
4. Confirma o ajusta con el operador.
5. Cierra con `confirm_order_for_client` cuando corresponda.

## Fixtures en esta carpeta

| Carpeta | Qué representa |
|---------|----------------|
| `01-owner-angeles-delivery-hoy` | Mensaje real del dueño: cliente ANGELES, delivery hoy, sweetcorn/green peas/fajitas |
| `02-owner-rey-chavez-miercoles` | Mensaje real del dueño: Rey Chavez 1, entrega miércoles, mamey/strawberry/mix berry/passion |

Los casos sintéticos de diseño anterior están en `casos-archivados/`.

## Cómo agregar casos nuevos

1. Creá `casos/NN-slug/caso.json` + `mensaje.txt` (o `mensaje_simulado.txt` para fotos).
2. Opcional: colocá `imagen.jpg` como referencia visual (el E2E usa el texto simulado).
3. Corré: `python scripts/test_agent_e2e.py --schema benfresh --suite real --seller --sequential`
4. Para variantes automáticas: agregá `--expand 3`
