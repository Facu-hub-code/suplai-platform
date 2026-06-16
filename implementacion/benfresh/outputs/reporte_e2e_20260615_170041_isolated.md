# Reporte de Testing E2E — Agente Suplai

Distribuidora: **benfresh**
Perfil de prueba: **Asistente de Vendedor**
Fecha de ejecución: **2026-06-15 17:00:41**
- **Suite:** journey — modo **isolated** (4 journeys, 15 pasos)

## 📊 Resumen Ejecutivo
- **Resultado Global:** 5/15 Aprobados (33.3%)
- **Latencia Promedio:** 35.65 segundos

| Caso # | Nombre del Caso | Aprobado | Latencia (s) | Tools llamadas |
| :--- | :--- | :---: | :---: | :--- |
| 1 | [Journey] Sergio's — carga, edición y consulta — Carga inicial del pedido `[journey p1]` | 🟢 PASS | 63.22 | `set_seller_selected_client`, `load_seller_order_text` |
| 2 | [Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas `[journey p2]` | 🟢 PASS | 70.65 | `set_seller_selected_client`, `load_seller_order_text`, `edit_order_for_client` |
| 3 | [Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced `[journey p3]` | 🟢 PASS | 62.44 | `set_seller_selected_client`, `load_seller_order_text`, `edit_order_for_client` |
| 4 | [Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto `[journey p4]` | 🔴 FAIL | 42.59 | `set_seller_selected_client`, `get_open_order_status_for_client` |
| 5 | [Journey] Nutrispa — foto, edición y consulta — Carga desde foto simulada `[journey p1]` | 🟢 PASS | 45.00 | `set_seller_selected_client`, `load_seller_order_text` |
| 6 | [Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach `[journey p2]` | 🟢 PASS | 61.21 | `set_seller_selected_client`, `load_seller_order_text`, `edit_order_for_client` |
| 7 | [Journey] Nutrispa — foto, edición y consulta — Consultar pedido `[journey p3]` | 🔴 FAIL | 37.95 | `set_seller_selected_client`, `edit_order_for_client` |
| 8 | [Journey] Powerfuel #2 — carga, edición y consulta — Carga inicial fresa y piña `[journey p1]` | 🔴 FAIL | 15.00 | *Ninguna* |
| 9 | [Journey] Powerfuel #2 — carga, edición y consulta — Duplicar fresa `[journey p2]` | 🔴 FAIL | 15.34 | *Ninguna* |
| 10 | [Journey] Powerfuel #2 — carga, edición y consulta — Quitar piña `[journey p3]` | 🔴 FAIL | 15.64 | *Ninguna* |
| 11 | [Journey] Powerfuel #2 — carga, edición y consulta — Consultar pedido `[journey p4]` | 🔴 FAIL | 15.64 | *Ninguna* |
| 12 | [Journey] Dixie — carga, edición y consulta — Carga inicial del pedido `[journey p1]` | 🔴 FAIL | 16.26 | *Ninguna* |
| 13 | [Journey] Dixie — carga, edición y consulta — Ajustar mixed veg y green beans `[journey p2]` | 🔴 FAIL | 24.44 | `set_seller_selected_client` |
| 14 | [Journey] Dixie — carga, edición y consulta — Agregar 1 sofrito `[journey p3]` | 🔴 FAIL | 24.61 | `set_seller_selected_client` |
| 15 | [Journey] Dixie — carga, edición y consulta — Consultar pedido `[journey p4]` | 🔴 FAIL | 24.80 | `set_seller_selected_client` |

## 📝 Detalle de Casos de Prueba

---

### Caso 1: [Journey] Sergio's — carga, edición y consulta — Carga inicial del pedido (🟢 PASS)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/03-sergios-carrot-broccoli` — journey `03-sergios-carrot-broccoli` paso 1/4
- **Mensaje enviado:** *"Cliente Sergio's
Pedido 
 Carrot sliced 20lb - 10
4 Vegetales - 15
Broccoli 22lb - 53"*
- **Comportamiento esperado:** Identificar Sergio's Catering y cargar carrot sliced 10, 4 vegetales 15 y broccoli 53.
- **Respuesta del bot:**
  > "He agregado los productos al pedido de Sergio's Catering. Aquí está el detalle:

1. **Carrot sliced 20 LB** (SKU 89090029) - 10 unidades
2. **4 vegetables Peas & Carrot & Sweetcorn & Green Beans 22 lb** (SKU 736952201911) - 15 unidades
3. **Broccoli frozen 22,04 lb** (SKU 74987455943) - 53 unidades

El total del pedido es de $2012.26. ¿Te gustaría confirmar el pedido o agregar algo más? 📦"
- **Latencia:** 63.22s

**Tools ejecutadas:**
- `set_seller_selected_client` (10630ms) - Status: `ok`
- `load_seller_order_text` (21896ms) - Status: `ok`

- **Análisis de Auditoría:**
  El bot identificó correctamente al cliente 'Sergio's Catering' y cargó los productos especificados en el mensaje. Se ejecutaron las herramientas 'set_seller_selected_client' y 'load_seller_order_text', lo que indica que el bot realizó las acciones necesarias para cargar el pedido. La respuesta del bot también fue coherente y detallada, proporcionando un resumen de los productos agregados y el total del pedido, además de ofrecer la opción de confirmar o agregar más productos. Esto cumple con el comportamiento esperado, por lo que se califica como pasado.

---

### Caso 2: [Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas (🟢 PASS)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/03-sergios-carrot-broccoli` — journey `03-sergios-carrot-broccoli` paso 2/4
- **Mensaje enviado:** *"Cliente Sergio's
Pedido 
 Carrot sliced 20lb - 10
4 Vegetales - 15
Broccoli 22lb - 53

Corrección: broccoli bajar a 40 cajas."*
- **Comportamiento esperado:** Ajustar cantidad de broccoli a 40 en el pedido abierto de Sergio's.
- **Respuesta del bot:**
  > "He ajustado el pedido para **Sergio's Catering**. Aquí está el detalle actualizado:

1. **SKU 89090029** · Carrot sliced 20 LB
   - 10 unidades × $20.20 → $202.00
2. **SKU 736952201911** · 4 vegetables Peas & Carrot & Sweetcorn & Green Beans 22 lb
   - 15 unidades × $26.45 → $396.75
3. **SKU 74987455943** · Broccoli frozen 22,04 lb
   - 40 cajas × $26.67 → $1066.80

**Total del pedido:** $1665.55.

¿Hay algo más que te gustaría ajustar o agregar? 📦"
- **Latencia:** 70.65s

**Tools ejecutadas:**
- `set_seller_selected_client` (9658ms) - Status: `ok`
- `load_seller_order_text` (16901ms) - Status: `ok`
- `edit_order_for_client` (20745ms) - Status: `ok`

- **Análisis de Auditoría:**
  El bot ha respondido correctamente a la solicitud de ajuste en el pedido de Sergio's Catering, reduciendo la cantidad de broccoli a 40 cajas. Se han llamado las herramientas adecuadas: 'load_seller_order_text' para cargar el pedido existente y 'edit_order_for_client' para realizar la modificación solicitada. Además, el bot ha proporcionado un resumen claro del pedido actualizado, lo que demuestra un comportamiento conversacional coherente y satisfactorio. Por lo tanto, el caso se califica como pasado.

---

### Caso 3: [Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced (🟢 PASS)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/03-sergios-carrot-broccoli` — journey `03-sergios-carrot-broccoli` paso 3/4
- **Mensaje enviado:** *"Cliente Sergio's
Pedido 
 Carrot sliced 20lb - 10
4 Vegetales - 15
Broccoli 22lb - 40

Agregá 2 cajas más de carrot sliced 20lb."*
- **Comportamiento esperado:** Agregar 2 cajas más de carrot sliced 20lb al pedido de Sergio's.
- **Respuesta del bot:**
  > "He agregado 2 cajas más de *Carrot sliced 20 LB* al pedido de Sergio's. Aquí está el detalle actualizado:

1. **SKU 89090029** · Carrot sliced 20 LB
   - 10 u. × $20.20 → $202.00
2. **SKU 736952201911** · 4 vegetables Peas & Carrot & Sweetcorn & Green Beans 22 lb
   - 15 u. × $26.45 → $396.75
3. **SKU 74987455943** · Broccoli frozen 22,04 lb
   - 40 u. × $26.67 → $1066.80
4. **SKU 89090029** · Carrot sliced 20 LB
   - 2 u. × $20.20 → $40.40

**Total del pedido:** $1705.95.

¿Te gustaría agregar algo más? 📦"
- **Latencia:** 62.44s

**Tools ejecutadas:**
- `set_seller_selected_client` (8345ms) - Status: `ok`
- `load_seller_order_text` (17180ms) - Status: `ok`
- `edit_order_for_client` (14117ms) - Status: `ok`

- **Análisis de Auditoría:**
  El bot respondió correctamente al mensaje del cliente, confirmando la adición de 2 cajas de 'Carrot sliced 20 LB' al pedido de Sergio's. Además, se ejecutaron las herramientas adecuadas: 'load_seller_order_text' para cargar el pedido existente y 'edit_order_for_client' para agregar los nuevos ítems. La respuesta del bot fue coherente y proporcionó un resumen del pedido actualizado, incluyendo el SKU correcto. Por lo tanto, el caso se considera aprobado.

---

### Caso 4: [Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/03-sergios-carrot-broccoli` — journey `03-sergios-carrot-broccoli` paso 4/4
- **Mensaje enviado:** *"Cliente Sergio's — ¿cómo quedó el pedido con carrot 12, 4 vegetales 15 y broccoli 40?"*
- **Comportamiento esperado:** Mostrar resumen del pedido de Sergio's con cantidades actualizadas (broccoli 40, carrot 12, 4 veg 15).
- **Respuesta del bot:**
  > "No hay ningún pedido abierto para Sergio's Catering en este momento. Si querés, puedo ayudarte a crear uno nuevo. ¿Te gustaría hacerlo?"
- **Latencia:** 42.59s

**Tools ejecutadas:**
- `set_seller_selected_client` (8069ms) - Status: `ok`
- `get_open_order_status_for_client` (13332ms) - Status: `error`

- **Análisis de Auditoría:**
  El bot no cumplió con el comportamiento esperado, ya que la respuesta indica que no hay ningún pedido abierto para Sergio's Catering, lo cual es incorrecto dado que el caso de prueba especifica que se debe mostrar un resumen del pedido con las cantidades actualizadas. Además, aunque se llamó a la herramienta 'get_open_order_status_for_client', esta falló, lo que impidió obtener la información necesaria para responder adecuadamente. La herramienta 'set_seller_selected_client' se ejecutó correctamente, pero no es suficiente para cumplir con el requerimiento del caso. Por lo tanto, la evaluación es 'passed: false'.

---

### Caso 5: [Journey] Nutrispa — foto, edición y consulta — Carga desde foto simulada (🟢 PASS)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/04-nutrispa-foto-lista` — journey `04-nutrispa-foto-lista` paso 1/3
- **Mensaje enviado:** *"[Consulta con foto por WhatsApp]
Texto del cliente: Cliente Nutrispa
Contenido visto en la imagen (para catálogo/pedido): **Cliente Nutrispa**

- FZ CORN 30 LB - 5 CS
- FZ GREEN BEANS 22 LB - 2 CS
- FZ SPINACH 24 LB - 1 CS"*
- **Comportamiento esperado:** Procesar foto simulada de Nutrispa: 5 CS corn 30lb, 2 CS green beans 22lb, 1 CS spinach 24lb.
- **Respuesta del bot:**
  > "He agregado los productos al pedido de **Catering Educational** (código 13053309321). Aquí está el detalle del pedido:

1. **SKU 89090009** · Sweetcorn frozen 30 lb
   - 5 cajas × $36.30 → **$181.50**
2. **SKU 89090130** · CUT GREEN BEANS 22 lb
   - 2 cajas × $23.14 → **$46.28**
3. **SKU 89090038** · Spinach Frozen IQF - Box 24lb (1x24lb)
   - 1 caja × $32.95 → **$32.95**

**Total del pedido:** $260.73.

¿Te gustaría confirmar este pedido o necesitas agregar algo más? 📦"
- **Latencia:** 45.00s

**Tools ejecutadas:**
- `set_seller_selected_client` (8605ms) - Status: `ok`
- `load_seller_order_text` (16108ms) - Status: `ok`

- **Análisis de Auditoría:**
  El bot ha procesado correctamente la información del mensaje enviado, reconociendo los productos y cantidades indicadas. Se ejecutaron las herramientas 'set_seller_selected_client' y 'load_seller_order_text', lo que indica que el bot ha configurado correctamente el cliente y ha cargado el texto del pedido. Aunque no se esperaban herramientas específicas para este caso, el uso de estas herramientas es adecuado y cumple con las expectativas del flujo. Además, el bot proporciona un resumen claro del pedido y pregunta al usuario si desea confirmar o agregar algo más, lo que muestra un comportamiento conversacional apropiado. Por lo tanto, se considera que el caso ha pasado satisfactoriamente.

---

### Caso 6: [Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach (🟢 PASS)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/04-nutrispa-foto-lista` — journey `04-nutrispa-foto-lista` paso 2/3
- **Mensaje enviado:** *"Cliente Nutrispa
Pedido:
- FZ CORN 30 LB - 5 CS
- FZ GREEN BEANS 22 LB - 2 CS
- FZ SPINACH 24 LB - 1 CS

Corrección: corn a 6 CS y spinach a 2 CS."*
- **Comportamiento esperado:** Subir corn a 6 CS y spinach a 2 CS en el pedido de Nutrispa.
- **Respuesta del bot:**
  > "El pedido para **Catering Educational** (código 13053309321) ha sido actualizado:

**Pedido #52** · estado **abierto** · **editado**

**Ítems:**
1. **SKU 89090130** · CUT GREEN BEANS 22 lb
   - 2 cajas × $23.14 → **$46.28**
2. **SKU 89090009** · Sweetcorn frozen 30 lb
   - 6 cajas × $36.30 → **$217.80**
3. **SKU 89090038** · Spinach Frozen IQF - Box 24lb (1x24lb)
   - 2 cajas × $32.95 → **$65.90**

**Total pedido:** **$329.98**.

¿Te gustaría agregar algo más o confirmar el pedido? 📦"
- **Latencia:** 61.21s

**Tools ejecutadas:**
- `set_seller_selected_client` (8345ms) - Status: `ok`
- `load_seller_order_text` (16311ms) - Status: `ok`
- `edit_order_for_client` (15164ms) - Status: `ok`

- **Análisis de Auditoría:**
  El bot ha respondido correctamente al mensaje de prueba, actualizando el pedido de Nutrispa según las instrucciones dadas. Se han llamado las herramientas adecuadas: 'load_seller_order_text' para cargar el texto del pedido original y 'edit_order_for_client' para realizar las modificaciones solicitadas, que incluyen aumentar la cantidad de corn a 6 CS y spinach a 2 CS. Además, el bot ha proporcionado un resumen claro del pedido actualizado y ha preguntado si el cliente desea agregar algo más o confirmar el pedido, lo que muestra un comportamiento conversacional adecuado. Por lo tanto, se considera que el caso ha pasado satisfactoriamente.

---

### Caso 7: [Journey] Nutrispa — foto, edición y consulta — Consultar pedido (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/04-nutrispa-foto-lista` — journey `04-nutrispa-foto-lista` paso 3/3
- **Mensaje enviado:** *"Cliente Nutrispa — resumen del pedido con corn 6 CS, green beans 2 CS y spinach 2 CS."*
- **Comportamiento esperado:** Resumir pedido Nutrispa con corn 6, green beans 2, spinach 2.
- **Respuesta del bot:**
  > "No hay un pedido abierto para Nutrispa en este momento. Si querés, puedo crear uno nuevo con los productos que mencionaste. ¿Te gustaría que lo haga?"
- **Latencia:** 37.95s

**Tools ejecutadas:**
- `set_seller_selected_client` (8077ms) - Status: `ok`
- `edit_order_for_client` (10872ms) - Status: `error`

- **Análisis de Auditoría:**
  El bot no cumplió con el comportamiento esperado de resumir el pedido de Nutrispa. En lugar de proporcionar un resumen del pedido, indicó que no había un pedido abierto y ofreció crear uno nuevo. Aunque la intención de ofrecer crear un pedido es válida, el caso de prueba requería simplemente resumir el pedido existente. Además, se ejecutó la herramienta 'edit_order_for_client', pero falló, lo que indica que no se pudo realizar la acción esperada de editar el pedido. Por lo tanto, el bot no cumplió con los requisitos del caso de prueba.

---

### Caso 8: [Journey] Powerfuel #2 — carga, edición y consulta — Carga inicial fresa y piña (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/05-powerfuel-fresa-pina` — journey `05-powerfuel-fresa-pina` paso 1/4
- **Mensaje enviado:** *"Powerfuel #2
1 fresa
1 piña"*
- **Comportamiento esperado:** Identificar Powerfuel #2 y cargar 1 fresa y 1 piña (bolsa/caja piña con stock).
- **Respuesta del bot:**
  > "Para poder procesar este pedido, necesito saber para qué cliente es. ¿Podrías indicarme el nombre o algún identificador del cliente?"
- **Latencia:** 15.00s

- **Análisis de Auditoría:**
  El bot no identificó correctamente el cliente 'POWERFUEL SMOOTHIE SHOP 2 INC.' a pesar de que el mensaje de prueba incluía la información necesaria para procesar el pedido. En lugar de cargar los SKUs esperados (1 fresa y 1 piña), el bot solicitó información adicional sobre el cliente, lo que indica una falta de comprensión del contexto del mensaje. Además, no se llamó a ninguna herramienta de carga, lo que es un requisito para este caso. Por lo tanto, la evaluación es negativa.

---

### Caso 9: [Journey] Powerfuel #2 — carga, edición y consulta — Duplicar fresa (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/05-powerfuel-fresa-pina` — journey `05-powerfuel-fresa-pina` paso 2/4
- **Mensaje enviado:** *"Powerfuel #2
1 fresa
1 piña

Corrección: duplicar fresa, total 2 fresas."*
- **Comportamiento esperado:** Dejar fresa en cantidad 2 en el pedido de Powerfuel.
- **Respuesta del bot:**
  > "Para poder procesar este pedido, necesito saber a qué cliente se lo vamos a asignar. ¿Podrías indicarme el nombre o algún identificador del cliente?"
- **Latencia:** 15.34s

- **Análisis de Auditoría:**
  El bot no respondió adecuadamente a la solicitud de duplicar la fresa en el pedido. En lugar de procesar la corrección solicitada, el bot pidió información adicional sobre el cliente, lo cual no era necesario en este contexto, ya que el caso de prueba especifica que se trata de un mensaje autocontenido. Además, no se llamó a ninguna herramienta de carga o edición, lo que es un requisito para este caso. Por lo tanto, la evaluación es que el bot no cumplió con las expectativas.

---

### Caso 10: [Journey] Powerfuel #2 — carga, edición y consulta — Quitar piña (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/05-powerfuel-fresa-pina` — journey `05-powerfuel-fresa-pina` paso 3/4
- **Mensaje enviado:** *"Powerfuel #2
2 fresa
1 piña

Corrección: sacar la piña del pedido."*
- **Comportamiento esperado:** Eliminar piña del pedido; debe quedar solo fresa x2.
- **Respuesta del bot:**
  > "Para poder realizar la corrección en el pedido, primero necesito identificar al cliente. ¿Podrías decirme el nombre o algún dato del cliente para proceder?"
- **Latencia:** 15.64s

- **Análisis de Auditoría:**
  El bot no cumplió con la intención del mensaje, que era eliminar la piña del pedido. En lugar de proceder con la corrección solicitada, el bot pidió identificar al cliente, lo cual no era necesario en este contexto, ya que el mensaje incluía toda la información requerida para realizar la acción. Además, no se llamó a ninguna herramienta de carga o edición del pedido, lo que es un requisito para este caso. Por lo tanto, la evaluación es negativa.

---

### Caso 11: [Journey] Powerfuel #2 — carga, edición y consulta — Consultar pedido (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/05-powerfuel-fresa-pina` — journey `05-powerfuel-fresa-pina` paso 4/4
- **Mensaje enviado:** *"Powerfuel #2 — confirmame el pedido: solo 2 fresas, sin piña."*
- **Comportamiento esperado:** Confirmar que el pedido de Powerfuel tiene solo 2 fresas, sin piña.
- **Respuesta del bot:**
  > "Primero, necesito identificar al cliente para confirmar el pedido. ¿Podrías decirme el nombre o algún dato del cliente?"
- **Latencia:** 15.64s

- **Análisis de Auditoría:**
  El bot no respondió adecuadamente a la solicitud de confirmar el pedido, ya que no proporcionó la información solicitada sobre las fresas y la piña. En lugar de confirmar el pedido, el bot pidió información adicional para identificar al cliente, lo cual no era necesario en este contexto, ya que el mensaje incluía suficiente información para proceder. Además, no se llamó a ninguna herramienta para consultar el estado del pedido, lo que era esperado en este caso. Por lo tanto, la respuesta no cumple con las expectativas y se califica como fallida.

---

### Caso 12: [Journey] Dixie — carga, edición y consulta — Carga inicial del pedido (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/06-dixie-black-beans-mix` — journey `06-dixie-black-beans-mix` paso 1/4
- **Mensaje enviado:** *"Dixie 
Black Beans-3
Plantains-4
Mixed Vegtables-8
Green Beans-8
Sofrito-2"*
- **Comportamiento esperado:** Identificar Dixie y cargar black beans 3, plantains 4, mixed vegetables 8, green beans 8, sofrito 2.
- **Respuesta del bot:**
  > "Primero, necesito identificar al cliente para poder procesar el pedido. ¿Podrías darme más detalles sobre "Dixie"? Puede ser el nombre completo, razón social, teléfono o algún otro identificador."
- **Latencia:** 16.26s

- **Análisis de Auditoría:**
  El bot no cumplió con la expectativa de cargar los ítems al pedido. En lugar de procesar la información proporcionada sobre los productos y cantidades, solicitó más detalles para identificar al cliente, lo cual no era necesario ya que el mensaje incluía la identificación del cliente 'Dixie'. Además, no se llamó a ninguna herramienta de carga, lo que indica que no se realizó ninguna acción para agregar los productos al pedido. Por lo tanto, la respuesta no fue satisfactoria y el caso se califica como fallido.

---

### Caso 13: [Journey] Dixie — carga, edición y consulta — Ajustar mixed veg y green beans (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/06-dixie-black-beans-mix` — journey `06-dixie-black-beans-mix` paso 2/4
- **Mensaje enviado:** *"Dixie 
Black Beans-3
Plantains-4
Mixed Vegtables-8
Green Beans-8
Sofrito-2

Corrección: mixed vegetables a 5 y green beans a 6."*
- **Comportamiento esperado:** Bajar mixed vegetables a 5 y green beans a 6 en el pedido de Dixie.
- **Respuesta del bot:**
  > "Hay varios clientes que coinciden con «Dixie». ¿A cuál te referís?

1) Catering Educational (código 13059625412)
2) Dixie Prueba (código 4949)
3) Supermarket (código 13052463998)
4) Supermarket (código 13055910780)
5) Catering Educational (código 15615880220)
6) KEY FOOD LAKE WORTH S DIXIE (código 15615476330)

Por favor, respondé con el número de la opción (1, 2, …), el código o el teléfono del cliente."
- **Latencia:** 24.44s

**Tools ejecutadas:**
- `set_seller_selected_client` (5713ms) - Status: `error`

- **Análisis de Auditoría:**
  El bot no respondió adecuadamente a la solicitud de corrección de los ítems en el pedido de Dixie. En lugar de procesar la corrección de los SKUs indicados, el bot se centró en desambiguar el cliente, lo cual no era necesario ya que el mensaje incluía el contexto suficiente para identificar al cliente. Además, no se llamó a ninguna herramienta de carga o edición de pedido, como 'edit_order_for_client' o 'load_seller_order_text', lo que resulta en un fallo en la ejecución esperada. La herramienta 'set_seller_selected_client' fue llamada, pero falló, lo que indica que el bot no pudo avanzar en la tarea requerida. Por lo tanto, la evaluación es 'passed: false'.

---

### Caso 14: [Journey] Dixie — carga, edición y consulta — Agregar 1 sofrito (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/06-dixie-black-beans-mix` — journey `06-dixie-black-beans-mix` paso 3/4
- **Mensaje enviado:** *"Dixie 
Black Beans-3
Plantains-4
Mixed Vegtables-5
Green Beans-6
Sofrito-2

Agregá 1 sofrito más."*
- **Comportamiento esperado:** Sumar 1 sofrito más (total 3) al pedido de Dixie.
- **Respuesta del bot:**
  > "Hay varios clientes que coinciden con «Dixie». ¿A cuál te referís?

1) Catering Educational (código 13059625412)
2) Dixie Prueba (código 4949)
3) Supermarket (código 13052463998)
4) Supermarket (código 13055910780)
5) Catering Educational (código 15615880220)
6) KEY FOOD LAKE WORTH S DIXIE (código 15615476330)

Por favor, respondé con el número de la opción (1, 2, …), el código o el teléfono del cliente."
- **Latencia:** 24.61s

**Tools ejecutadas:**
- `set_seller_selected_client` (5751ms) - Status: `error`

- **Análisis de Auditoría:**
  El bot no respondió adecuadamente a la solicitud de agregar un sofrito más al pedido de Dixie. En lugar de procesar la solicitud de carga de un SKU, el bot realizó una desambiguación incorrecta al preguntar a cuál cliente de los múltiples que coinciden con 'Dixie' se refería el usuario. Esto no es relevante para la intención del mensaje, que era simplemente agregar un ítem al pedido. Además, aunque se llamó a la herramienta 'set_seller_selected_client', esta falló y no se ejecutaron herramientas de carga como 'edit_order_for_client' o 'load_seller_order_text'. Por lo tanto, el caso se califica como 'passed: false'.

---

### Caso 15: [Journey] Dixie — carga, edición y consulta — Consultar pedido (🔴 FAIL)
- **Origen:** journey — fixture `implementacion/benfresh/journeys/06-dixie-black-beans-mix` — journey `06-dixie-black-beans-mix` paso 4/4
- **Mensaje enviado:** *"Dixie — resumen del pedido: beans 3, plantains 4, mixed veg 5, green beans 6, sofrito 3."*
- **Comportamiento esperado:** Resumir pedido Dixie: beans 3, plantains 4, mixed veg 5, green beans 6, sofrito 3.
- **Respuesta del bot:**
  > "Hay varios clientes que coinciden con «Dixie». ¿A cuál te referís?

1) Catering Educational (código 13059625412)
2) Dixie Prueba (código 4949)
3) Supermarket (código 13052463998)
4) Supermarket (código 13055910780)
5) Catering Educational (código 15615880220)
6) KEY FOOD LAKE WORTH S DIXIE (código 15615476330)

Por favor, respondé con el número de la opción (1, 2, …), el código o el teléfono del cliente."
- **Latencia:** 24.80s

**Tools ejecutadas:**
- `set_seller_selected_client` (5605ms) - Status: `error`

- **Análisis de Auditoría:**
  El bot no respondió adecuadamente a la consulta sobre el resumen del pedido de Dixie. En lugar de proporcionar un resumen del pedido, el bot solicitó aclaración sobre a cuál cliente de los múltiples que coinciden con 'Dixie' se refería el usuario. Esto indica que el bot no entendió correctamente el contexto del mensaje, que era un resumen del pedido y no una solicitud de información sobre clientes. Además, aunque se ejecutó la herramienta 'set_seller_selected_client', esta falló y no se llamó a ninguna herramienta adecuada para consultar el estado del pedido, lo que es necesario en este caso. Por lo tanto, el resultado es 'passed: false'.


### ⚡ Recomendaciones de Optimización Proactivas:
#### 🛠️ Errores detectados:
- La herramienta 'get_open_order_status_for_client' falló en '[Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto': None
- La herramienta 'edit_order_for_client' falló en '[Journey] Nutrispa — foto, edición y consulta — Consultar pedido': None
- La herramienta 'set_seller_selected_client' falló en '[Journey] Dixie — carga, edición y consulta — Ajustar mixed veg y green beans': None
- La herramienta 'set_seller_selected_client' falló en '[Journey] Dixie — carga, edición y consulta — Agregar 1 sofrito': None
- La herramienta 'set_seller_selected_client' falló en '[Journey] Dixie — carga, edición y consulta — Consultar pedido': None
#### 🐢 Cuellos de botella de latencia:
- Caso '[Journey] Sergio's — carga, edición y consulta — Carga inicial del pedido' superó 8s de latencia (Medido: 63.22s).
- La herramienta 'set_seller_selected_client' demoró 10.63s en '[Journey] Sergio's — carga, edición y consulta — Carga inicial del pedido'.
- La herramienta 'load_seller_order_text' demoró 21.90s en '[Journey] Sergio's — carga, edición y consulta — Carga inicial del pedido'.
- Caso '[Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas' superó 8s de latencia (Medido: 70.65s).
- La herramienta 'set_seller_selected_client' demoró 9.66s en '[Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas'.
- La herramienta 'load_seller_order_text' demoró 16.90s en '[Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas'.
- La herramienta 'edit_order_for_client' demoró 20.75s en '[Journey] Sergio's — carga, edición y consulta — Reducir broccoli a 40 cajas'.
- Caso '[Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced' superó 8s de latencia (Medido: 62.44s).
- La herramienta 'set_seller_selected_client' demoró 8.35s en '[Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced'.
- La herramienta 'load_seller_order_text' demoró 17.18s en '[Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced'.
- La herramienta 'edit_order_for_client' demoró 14.12s en '[Journey] Sergio's — carga, edición y consulta — Sumar 2 cajas carrot sliced'.
- Caso '[Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto' superó 8s de latencia (Medido: 42.59s).
- La herramienta 'set_seller_selected_client' demoró 8.07s en '[Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto'.
- La herramienta 'get_open_order_status_for_client' demoró 13.33s en '[Journey] Sergio's — carga, edición y consulta — Consultar pedido abierto'.
- Caso '[Journey] Nutrispa — foto, edición y consulta — Carga desde foto simulada' superó 8s de latencia (Medido: 45.00s).
- La herramienta 'set_seller_selected_client' demoró 8.61s en '[Journey] Nutrispa — foto, edición y consulta — Carga desde foto simulada'.
- La herramienta 'load_seller_order_text' demoró 16.11s en '[Journey] Nutrispa — foto, edición y consulta — Carga desde foto simulada'.
- Caso '[Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach' superó 8s de latencia (Medido: 61.21s).
- La herramienta 'set_seller_selected_client' demoró 8.34s en '[Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach'.
- La herramienta 'load_seller_order_text' demoró 16.31s en '[Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach'.
- La herramienta 'edit_order_for_client' demoró 15.16s en '[Journey] Nutrispa — foto, edición y consulta — Ajustar corn y spinach'.
- Caso '[Journey] Nutrispa — foto, edición y consulta — Consultar pedido' superó 8s de latencia (Medido: 37.95s).
- La herramienta 'set_seller_selected_client' demoró 8.08s en '[Journey] Nutrispa — foto, edición y consulta — Consultar pedido'.
- La herramienta 'edit_order_for_client' demoró 10.87s en '[Journey] Nutrispa — foto, edición y consulta — Consultar pedido'.
- Caso '[Journey] Powerfuel #2 — carga, edición y consulta — Carga inicial fresa y piña' superó 8s de latencia (Medido: 15.00s).
- Caso '[Journey] Powerfuel #2 — carga, edición y consulta — Duplicar fresa' superó 8s de latencia (Medido: 15.34s).
- Caso '[Journey] Powerfuel #2 — carga, edición y consulta — Quitar piña' superó 8s de latencia (Medido: 15.64s).
- Caso '[Journey] Powerfuel #2 — carga, edición y consulta — Consultar pedido' superó 8s de latencia (Medido: 15.64s).
- Caso '[Journey] Dixie — carga, edición y consulta — Carga inicial del pedido' superó 8s de latencia (Medido: 16.26s).
- Caso '[Journey] Dixie — carga, edición y consulta — Ajustar mixed veg y green beans' superó 8s de latencia (Medido: 24.44s).
- La herramienta 'set_seller_selected_client' demoró 5.71s en '[Journey] Dixie — carga, edición y consulta — Ajustar mixed veg y green beans'.
- Caso '[Journey] Dixie — carga, edición y consulta — Agregar 1 sofrito' superó 8s de latencia (Medido: 24.61s).
- La herramienta 'set_seller_selected_client' demoró 5.75s en '[Journey] Dixie — carga, edición y consulta — Agregar 1 sofrito'.
- Caso '[Journey] Dixie — carga, edición y consulta — Consultar pedido' superó 8s de latencia (Medido: 24.80s).
- La herramienta 'set_seller_selected_client' demoró 5.61s en '[Journey] Dixie — carga, edición y consulta — Consultar pedido'.

*Recomendación:* Evalúe si hay herramientas activadas innecesarias y desactívelas mediante `healthcheck_schema.py` con `--fix-tools`.