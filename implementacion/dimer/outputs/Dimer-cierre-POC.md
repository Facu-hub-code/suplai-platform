# Dimer × Suplai — cierre de POC

**De la prueba a la implementación**  
Septiembre 2026 · WhatsApp comercial

Este documento resume lo que se envió, lo que contestaron y por qué la calidad de la data cambia el resultado. Sirve para cerrar la prueba de concepto y acordar la implementación real.

---

## 1. Los dos mensajes que se enviaron

Hubo **tres eventos de envío** y **dos plantillas**. Los eventos 1 y 2 usan el mismo texto (papas McCain). El evento 3 usa el aviso de vendedor y jefe zonal, con nombre, vendedor y teléfono ya limpios.

### Mensaje 1 — recuperación de papas McCain

Plantilla `prueba_01`. Variable: nombre de pila. Se envió dos veces (Grupo 1 el 18/08 y Grupo 2 el 25/08).

> **Dimer** ✓✓
>
> Hola María, cómo estás? Nos dimos cuenta que hace un tiempo no nos pides Papas, quería saber qué pasó, tuviste algún problema?

Es un mensaje que **pregunta**. Por eso conviene una tasa de respuesta más alta: invita a contar qué pasó.

### Mensaje 2 — vendedor de zona y jefe de ventas

Plantilla `dimer_litoral_contacto_v2`. Variables: nombre, vendedor, teléfono. Un solo envío, el 7/09, a la cartera Litoral.

> **Dimer** ✓✓
>
> Hola, Cristian! Te escribo de parte del equipo de Dimer
>
> Queríamos dejarte a mano el contacto directo de Doralisa Vivencio, que es tu vendedor asignado para ver cualquier pedido o duda de tu zona: +56 9 7988 8434
> De todas formas, si en algún momento no logras dar con Doralisa Vivencio, puedes escribirle directamente a Francisco Díaz, nuestro jefe de ventas, al +56 9 6191 6961.
> Cualquier cosa que necesites me avisas por acá! Que tengas un excelente día.

Es un mensaje que **avisa un contacto**. No pide explicación. Quien responde suele agradecer, reaccionar o, si la data está bien, pasar directo a un pedido.

---

## 2. Tres eventos, dos mensajes

| | Evento 1 | Evento 2 | Evento 3 |
|---|---|---|---|
| Fecha (Chile) | 18 ago 2026 | 25 ago 2026 | 7 sep 2026 |
| Mensaje | Papas McCain | Papas McCain *(el mismo)* | Vendedor + jefe zonal |
| Cartera | 30 personas naturales «perdidas» de papas | 50 personas naturales, sin repetir el Grupo 1 | 957 locales Litoral con vendedor asignado |
| Data previa | Nombre de pila inferido; padrón de «perdidos» ruidoso | Igual que el evento 1 | Nombre, vendedor y teléfono **curados** antes de enviar |
| Enviados (Meta aceptó) | 30 / 30 | 50 / 50 | 957 / 957 |

Los eventos 1 y 2 se leen juntos: mismo copy, misma hipótesis comercial, distinta oleada. El evento 3 es otra operación, con otra data.

---

## 3. Indicadores por evento

Ventana de respuesta: **48 horas** después del envío. Duración: primer bloque de la conversación (se corta si hay más de 10 minutos de silencio).

| Indicador | Evento 1 · McCain | Evento 2 · McCain | Evento 3 · Litoral |
|---|---|---|---|
| Enviados | 30 | 50 | 957 |
| Respondieron | 6 | 14 | 62 |
| **Tasa de respuesta** | **20%** | **28%** | **6,5%** |
| Duración mediana del hilo | 0,4 min | 1,4 min | 0,1 min |
| 90% de los hilos | — | 3,2 min | 6,2 min |
| Hilos resueltos en ≤ 3 min | — | 12 de 14 | 51 de 62 (82%) |
| Tiempo activo total del canal | 5 min | 17 min | **64 min** |
| Pedidos confirmados atribuibles | 1 · $104.360 | 0 el mismo día *(Álvaro cerró el 6/09 por $271.898)* | **4 · $1.637.253** |

### Cómo leer la tasa de respuesta

No se comparan 20–28% contra 6,5% como si fueran el mismo aviso.

- En McCain el texto **pregunta** («qué pasó, tuviste algún problema?»). Eso empuja a contestar.
- En Litoral el texto **deja un teléfono**. Contestar es opcional: 28 de 62 primeras respuestas fueron un gracias o una reacción.
- Lo que sí se compara es **qué tan útil fue cada conversación** y **cuántos pedidos salieron** cuando el destinatario, el nombre y el vendedor coincidían.

### Los 4 pedidos del evento 3 (origen Suplai, post envío)

| Día | Local | Monto |
|---|---|---|
| 7/09 | Restaurante (Litoral, recibió el HSM) | $1.152.024 |
| 7/09 | Comercial (Litoral, recibió el HSM) | $173.474 |
| 7/09 | Felipe (Litoral, recibió el HSM) | $26.090 |
| 9/09 | Cristian (Litoral, recibió el HSM) | $285.665 |
| | **Total** | **$1.637.253** |

---

## 4. El tercer evento rindió más — porque la data venía bien

Juntando los dos envíos McCain: **1 pedido documentado en la oleada** ($104.360) frente a **4 pedidos** ($1.637.253) en Litoral.

| Contra los eventos 1+2 | Evento 3 |
|---|---|
| Pedidos confirmados | **+300%** (4 vs 1) |
| Monto confirmado | **15,7 veces** ($1.637.253 vs $104.360) |

No es magia del canal. En agosto el padrón de «clientes perdidos de papas» estaba sucio: varios que contestaron **seguían comprando**, ya tenían vendedor (Gonzalo, Fernanda) o pedían en Belloto. El agente lo detectó en el chat, pero el mensaje partía de un diagnóstico incorrecto.

En Litoral se hizo el trabajo al revés: RUT, celular, nombre de pila, vendedor de ruta y teléfono del vendedor **antes** de apretar enviar. El 7/09 el cliente recibió *su* vendedor, no un «¿por qué no nos comprás?». Quien tenía ganas de pedir, pidió. Quien solo necesitaba el contacto, guardó el número.

**Incapié para la implementación:** el WhatsApp multiplica lo que hay en la base. Si el vendedor está mal, el teléfono está mal o el local no es persona natural cuando debería, el canal escala el error. Si la data llega correcta, escala el pedido.

---

## 5. Minutos del canal vs minutos de un vendedor

Pregunta de la POC: ¿cuánto cuesta **entender en qué está cada cliente**?

| | Canal WhatsApp (evento 3) | Un vendedor, a mano |
|---|---|---|
| Avisar el contacto a 957 locales | **6 minutos** de envío (14:00–14:06 Chile) | **~80 horas** si dedica 5 min a cada uno (~10 días hábiles) |
| Entender a los 62 que contestaron | **64 minutos** de conversación activa | **~8 horas** si dedica 8 min a cada llamado |

El 82% de quienes respondieron en Litoral quedó resuelto en menos de 3 minutos. Un vendedor no puede hacer esa pasada sobre 957 puntos el mismo lunes. El canal sí: deja el contacto, clasifica al que escribe y le pasa el pedido al equipo.

Eso es lo que queremos repetir en la implementación: **data limpia in → conversación corta y útil out**.

---

## 6. Qué pedimos para pasar a implementación

1. **Un padrón único de clientes** con RUT, celular WhatsApp, nombre de pila o razón social, vendedor vigente y comuna/ruta. Sin esa fila, no hay plantilla que rinda.
2. **Dueño de la data en Dimer** (quién corrige un teléfono mal cargado y en cuánto tiempo).
3. **Calendario de avisos** (preventa, cambio de ruta, promo, recupero) con la misma regla: se cura, se mira una muestra, se envía.
4. **Cierre comercial humano** para los casos que el canal deja picando (precio vs competencia, visita pendiente, local cerrado). El agente abre; el vendedor cierra lo que no es un pedido inmediato.

La POC ya mostró el formato de los mensajes, tres oleadas y el salto cuando la base está curada. El siguiente paso es operar así todas las semanas, no una vez.

---

*Fuentes: envíos aceptados por Meta (`envios_plantillas`), respuestas en 48 h (`core.conversation_events`), pedidos confirmados origen Suplai, y el informe de recuperación McCain del 25/08/2026. Sin teléfonos en este documento.*
