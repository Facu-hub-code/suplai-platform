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
   - **Texto libre** con cantidades y productos → `load_seller_order_text`
   - **Foto de lista** (manuscrita o captura) → visión + `load_seller_order_text` (texto OCR en el mensaje)
4. Confirma o ajusta con el operador.
5. Cierra con `confirm_order_for_client` cuando corresponda.

## Fixtures en esta carpeta

| Carpeta | Qué representa |
|---------|----------------|
| `01-owner-angeles-delivery-hoy` | Mensaje real del dueño: cliente ANGELES, delivery hoy, sweetcorn/green peas/fajitas |
| `02-owner-rey-chavez-miercoles` | Mensaje real del dueño: Rey Chavez 1, entrega miércoles, mamey/strawberry/mix berry/passion |
| `03-sergios-carrot-broccoli` | Sergio's Catering: carrot sliced 20lb, 4 vegetales, broccoli 22lb |
| `04-nutrispa-foto-lista` | Nutrispa: foto WhatsApp con corn 30lb, green beans 22lb, spinach 24lb (OCR simulado) |
| `05-powerfuel-fresa-pina` | Powerfuel #2: pedido mínimo smoothie (1 fresa, 1 piña) |
| `06-dixie-black-beans-mix` | Dixie: black beans, plantains, mixed vegetables, green beans, sofrito |

Los casos sintéticos de diseño anterior están en `casos-archivados/`.

## Journeys multi-paso (`../journeys/`)

Cada caso real 03–06 tiene un **journey** con pasos encadenados: carga → edición de cantidades → consulta.

| Journey | Pasos |
|---------|-------|
| `03-sergios-carrot-broccoli` | carga → broccoli 40 → +2 carrot → consulta |
| `04-nutrispa-foto-lista` | foto → corn 6 / spinach 2 → consulta |
| `05-powerfuel-fresa-pina` | carga → 2 fresas → quitar piña → consulta |
| `06-dixie-black-beans-mix` | carga → mix/green beans → +1 sofrito → consulta |

```bash
# Encadenado (misma sesión por escenario)
python scripts/fase-09-e2e/test_agent_e2e.py --schema benfresh --suite journey --seller --journey-mode chained

# Aislado (cleanup por paso; mensajes autocontenidos en ediciones)
python scripts/fase-09-e2e/test_agent_e2e.py --schema benfresh --suite journey --seller --journey-mode isolated
```

## Cómo agregar casos nuevos

1. Creá `casos/NN-slug/caso.json` + `mensaje.txt` (o `mensaje_simulado.txt` para fotos).
2. Opcional: colocá `imagen.jpg` como referencia visual (el E2E usa el texto simulado).
3. Corré: `python scripts/fase-09-e2e/test_agent_e2e.py --schema benfresh --suite real --seller --sequential`
4. Para variantes automáticas: agregá `--expand 3`
