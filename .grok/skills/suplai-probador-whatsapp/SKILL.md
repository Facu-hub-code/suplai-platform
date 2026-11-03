---
name: suplai-probador-whatsapp
description: >-
  Use when the Probador bot tests, from Faka's WhatsApp Web, whether the sales
  agent of dimer, almaro or gonzales finds the new products. Includes the
  anti-ban rules for the WhatsApp account. Only the Probador uses this skill.
when-to-use: probar agente, whatsapp, novedades, probador
---

# Probador por WhatsApp

Le preguntás al agente de cada tenant por las novedades listas, como lo haría un cliente, y anotás si las encuentra. Usás **el WhatsApp personal de Faka**: si WhatsApp lo bloquea por automatización, Faka pierde su cuenta. Estas reglas están por encima de cualquier otra tarea.

## Reglas anti-bloqueo (DEV-211)

1. **Solo vos abrís WhatsApp Web.** Si la sesión no está abierta o pide el QR, parás y le pedís a Faka que tome el control y lo escanee. Nunca lo intentás solo.
2. **Solo escribís a los 3 números de los agentes.** Los números están en `~/suplai-bots/estado/probador-numeros.json`, que carga Faka. No abrís otros chats, no escribís a clientes ni a grupos, no reenviás nada y no mandás links, fotos ni audios.
3. **Topes por día:** una charla por tenant, hasta 6 mensajes por tenant y 20 en total. Llevá la cuenta en `~/suplai-bots/estado/probador-{AAAA-MM-DD}.json` y leela antes de cada mensaje.
4. **Ritmo humano:** entre 20 y 60 segundos al azar entre mensajes. Tipeás el texto, no lo pegás en bloque. Mensajes cortos, como un cliente. Un tenant a la vez.
5. **Horario:** de 10 a 19, hora de Argentina, de lunes a viernes.
6. **Nunca confirmás un pedido.** Si el agente arma un carrito o pide confirmación, contestás "por ahora no, gracias" y cerrás.
7. **Señal de alarma = parar todo:** cualquier aviso de WhatsApp, captcha, "cuenta en riesgo", "actividad inusual", un cierre de sesión o un chat que no carga. No reintentás. Le avisás al jefe para que abra una issue urgente a Faka.

## Pasos

1. Leé las novedades listas del día en `~/suplai-bots/novedades/{AAAA-MM-DD}-{schema}.json` (`lista` verdadero). Elegí hasta 3 por tenant, mejor de categorías distintas.
2. Para cada una, armá una pregunta de cliente con el nombre coloquial y no con el código: "hola, ¿tenés las barritas Cereal Mix Pro de chocolate?".
3. Anotá por producto si lo encontró (sí, no o lo confundió con otro), qué precio dijo, si lo ofreció solo o tuviste que insistir, y una cita corta de la respuesta.
4. Compará el precio con Supabase (solo lectura): `precios_productos` de la lista del cliente.
5. Guardá el resultado en `~/suplai-bots/pruebas/{AAAA-MM-DD}-{schema}.json` y pasáselo al jefe.

## Resumen para el jefe

Por tenant: probadas, encontradas, no encontradas (con la causa probable: alias, descripción, embedding o stock) y precios que no coinciden. Además, mensajes usados contra el tope del día y cualquier señal rara de WhatsApp.
