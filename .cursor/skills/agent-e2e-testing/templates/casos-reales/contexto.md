# Caso de uso — {nombre_distribuidora}

## Situación actual (AS-IS)

Describí cómo opera hoy el distribuidor: quién envía mensajes, qué canal usan, qué se hace a mano.

Ejemplo Benfresh: los vendedores reenvían pedidos por WhatsApp a un teléfono central; un operador los transcribe al sistema.

## Objetivo (TO-BE)

Qué debe automatizar el agente: identificar cliente, interpretar lista (texto o foto), armar pedido, confirmar.

## Perfil de prueba

- Modo: `seller` (asistente de vendedor) o `client` (cliente final).
- Teléfono de prueba: variable `E2E_SELLER_PHONE` o cliente `suplai-platform-test`.

## Notas para generación de variantes

Frases típicas, abreviaturas, unidades (kg, cajas, bultos), errores comunes que el agente debe tolerar.
