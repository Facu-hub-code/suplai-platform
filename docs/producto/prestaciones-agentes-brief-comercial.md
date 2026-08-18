# Prestaciones de los agentes Suplai

**Audiencia:** comercial / preventa  
**Formato:** listado por agente, título + 1–2 líneas (pie para el pitch)  
**Fecha:** 17 de agosto de 2026  
**Origen del pedido:** brief oral — listado de prestaciones, no un documento entrelazado

Este documento describe **qué puede hacer cada “agente”** frente a un cliente de la distribuidora. Está pensado para armar argumento comercial y, si hace falta, un paseo de producto. No es arquitectura ni inventario técnico.

---

## Cómo leer este listado

En la práctica hay **una línea de WhatsApp por distribuidora**. El sistema reconoce quién escribe (punto de venta, vendedor o número desconocido) y entra en el rol que corresponde.

Los cuatro agentes que pide el brief son **roles de producto**, no cuatro bots distintos:

| Rol comercial | Quién lo usa | Qué resuelve |
|---|---|---|
| Recepcionista | Número nuevo / cliente no dado de alta | Identificar y registrar el comercio antes de vender |
| Vendedor | Punto de venta (PdV) | Recibir el pedido por el teléfono, como si hablara con un vendedor |
| Soporte de vendedor | Preventista / vendedor de calle | Pasar pedidos de su cartera, consultar y ver métricas |
| Marketing | Supervisor / dueño + el PdV que recibe el mensaje | Traer demanda, reactivar y atribuir campaña → conversación → pedido |

**Métricas** no es un quinto bot. Es la capa de inteligencia (back office + Copilot) que alimenta al soporte de vendedor y al argumento de marketing. Va en una sección propia al final, como pedía el brief.

**Canales complementarios** (no son agentes, pero cierran el pitch):

- **Tienda web B2B** — el PdV puede terminar el pedido en catálogo si prefiere no chatear.
- **Suplai Field** — app del vendedor (ruta, tareas, torneos). El chat le manda el link.

---

## 1. Agente recepcionista

Atiende al que escribe por primera vez y no está en la base. Recolecta lo mínimo para darlo de alta y recién ahí lo pasa al flujo de venta. Evita que un comercio nuevo “se caiga” porque nadie lo cargó en el ERP.

### 1.1 Alta conversacional del comercio

El número desconocido no queda en el limbo: el recepcionista pide los datos, valida si ya existe y crea o actualiza el cliente.

### 1.2 Modo low-friction

Si la distribuidora lo configura, puede pedir solo razón social (u otro set mínimo) y no un formulario largo. Baja la fricción del primer contacto.

### 1.3 Continuidad hacia la venta

Cuando el alta cierra, el mismo WhatsApp sigue como agente vendedor. El PdV no tiene que “empezar de nuevo” en otro número.

### 1.4 Registro también desde la tienda

Si el comercio llega por el catálogo web, puede darse de alta ahí y retomar la compra. Mismo cliente, dos puertas de entrada.

---

## 2. Agente vendedor (modo punto de venta)

Es el que el comercio usa para **pedir por el número de WhatsApp**, en lenguaje natural. Reemplaza la llamada al vendedor, el audio al grupo y la planilla. El PdV escribe “mandame 10 cajas de X y 2 de Y” y el agente arma el pedido.

### 2.1 Recibir el pedido por teléfono / WhatsApp

Texto, nota de voz o foto de lista/góndola. El agente entiende el pedido, busca productos y carga el carrito. Es la prestación central del pitch.

### 2.2 Catálogo y precios del cliente

Responde “¿tenés…?”, “¿cuánto sale…?”, “¿qué hay en…?” con precio de **la lista de ese PdV**, no un precio genérico. Si no hay stock, lo dice; no promete lo que no se puede entregar.

### 2.3 Armar, editar y confirmar el pedido

Crea o reutiliza el pedido abierto, agrega o saca ítems, muestra subtotal y confirma. Un solo hilo: no hay que rearmar el pedido en otro sistema.

### 2.4 Promociones aplicadas en el momento

Lista las promos vigentes de ese cliente y las aplica al confirmar (precio fijo, %, mix & match). El PdV ve el beneficio en el mismo chat.

### 2.5 Subir el ticket (mínimo de compra y sugerencias)

Si falta para el mínimo, sugiere qué agregar. También puede proponer complementarios o un upgrade (cross / up-sell) según reglas de la distribuidora.

### 2.6 Estado del pedido e historial

“¿Qué tengo cargado?”, “¿cómo quedó el de ayer?”, últimos pedidos. El comercio no depende de llamar para saber dónde está.

### 2.7 Link a la tienda

Si el PdV prefiere mirar el catálogo, el agente manda un link con el teléfono ya identificado. El carrito es el mismo pedido abierto.

### 2.8 Entrega B2C (cuando el tenant es B2C o híbrido)

Cotiza envío por zona/GPS o configura retiro. No confirma a ciegas si falta definir cómo se entrega.

### 2.9 Escalamiento humano

Si el caso se sale de la automatización (reclamo, excepción, algo que el bot no debe resolver), abre un ticket a la distribuidora.

### 2.10 Cierre operativo

Al confirmar: validaciones (mínimo, stock, precio), notificación, y —si está conectado— empuje al ERP. El pedido no se queda “en el chat”.

---

## 3. Agente soporte de vendedor

Es el asistente del **preventista**. El vendedor le escribe al mismo tipo de número (o al canal vendedor) y opera **sobre su cartera**, no como si fuera un PdV. Sirve para pasar el pedido en la calle, consultar y pedir números sin abrir el back office.

### 3.1 Pasar el pedido del cliente

El vendedor elige el PdV (nombre, código, teléfono) y carga el pedido en texto libre, audio o foto. El sistema parsea líneas, resuelve SKUs y deja el pedido del **cliente**, no del WhatsApp del vendedor.

### 3.2 Editar y confirmar por el vendedor

Corrige cantidades, saca un ítem y confirma. La confirmación entra por el mismo pipeline que Field (tareas, puntos, ERP). No es un “anotador”: cierra venta.

### 3.3 Consultas de catálogo y precio en ruta

Stock, precio para un cliente, novedades, promos, lista y mínimo. El vendedor responde en el mostrador sin llamar a depósito ni abrir una planilla.

### 3.4 Ficha rápida del PdV

Último pedido, resumen de compra, datos de contacto, estado de WhatsApp. Contexto comercial en un mensaje, antes de entrar al local.

### 3.5 Métricas del vendedor (en el chat)

Ruta del día, tareas, objetivos, torneo, ventas. Es la respuesta a “¿hay un agente de métricas?”: **sí, vive acá**, en el soporte de vendedor. No hace falta otro bot.

### 3.6 Pedidos abiertos y sync ERP

Qué tiene abierto, qué falló al mandar al ERP. El vendedor ve el problema en WhatsApp y no se entera dos días después.

### 3.7 Puente a Suplai Field

Manda el link de la app (ruta, tareas, torneos, ficha de PdV). El chat cubre lo urgente; Field cubre la jornada.

### 3.8 Briefing diario en audio (si está prendido)

Audio corto a la mañana: ruta, tareas, objetivos, torneo. El vendedor arranca el día sin entrar a un dashboard.

---

## 4. Agente de marketing

No es un chat que “vende creatividades”. Es el motor que **trae y reactiva demanda** hacia el WhatsApp del agente vendedor, y que el supervisor arma desde el back office. El brief lo marca con potencial alto: el pedido entra por el mismo número que ya toma la orden.

### 4.1 Campañas WhatsApp programadas (agenda)

El supervisor arma envíos de plantillas Meta a clientes o grupos, en día y horario. El PdV recibe el mensaje y, si contesta, cae en el agente vendedor. Campaña → conversación → pedido, en un solo hilo.

### 4.2 Segmentación para el disparo

Grupos por lista, día de visita, etiquetas, zona. No es un blast a toda la base: se elige a quién se le habla.

### 4.3 Follow-up automático

Secuencias cuando el chat quedó quieto, hay pedido abierto sin confirmar o no hubo respuesta. Recupera la venta que se enfría, sin que alguien recuerde “hay que escribirle”.

### 4.4 Promos y exclusivas como gancho

Las mismas promociones del catálogo se usan de contenido: “esta semana X está en promo”. El marketing no es un folleto suelto; está atado al precio que el agente va a cobrar.

### 4.5 Click-to-WhatsApp / Meta Ads (módulo en curso)

Anuncios que abren el WhatsApp de la distribuidora, con targeting por zona de cobertura y medición del embudo impresiones → clics → conversaciones → pedidos. **Estado:** en implementación (creatividades, campañas, dashboard, atribución `ctwa_clid`). Se puede adelantar en reunión como dirección del producto; no venderlo como live en todos los tenants.

### 4.6 Atribución campaña → pedido

La conversación que nació de un anuncio o de una plantilla se puede cruzar con el pedido. Eso es lo que permite hablar de CAC y de “esta campaña trajo N pedidos”, no solo de likes.

### 4.7 Notificaciones de ciclo de pedido

Plantilla al confirmar, email con PDF, recordatorios. Marketing operativo: el cliente queda informado y el canal sigue vivo para el próximo pedido.

---

## 5. Métricas e inteligencia (la capa que faltaba en el brief)

No es un agente que el PdV “habla”. Es lo que el **dueño / supervisor** usa para dirigir, y lo que el soporte de vendedor resume en el chat. Pie de argumento: “no solo tomamos el pedido; mostramos qué está pasando”.

### 5.1 Copilot del back office

Preguntas en lenguaje natural: top productos, mayor pedido, este mes vs. el anterior, ritmo por día y por vendedor. Responde con tablas, KPIs, gráficos y mapa. El supervisor no espera el Excel del lunes.

### 5.2 Embudo del agente WhatsApp

Conversaciones iniciadas → entregadas → leídas → respondidas → carritos → pedidos confirmados. Sirve para defender ROI del número: no es un bot de FAQ, es un canal con conversión.

### 5.3 Performance de plantillas y campañas

Qué template se entregó, se leyó y terminó en pedido. Cruza marketing con resultado, no con vanidad.

### 5.4 Métricas del vendedor (ya listadas en 3.5)

Ruta, tareas, objetivos, torneo, ventas. El preventista las pide por WhatsApp; el supervisor las ve en Field / back office.

### 5.5 Insights y tickets

El agente (o un operador) abre tickets de calidad, logística, comercial o administración. La conversación deja un caso, no solo un chat.

### 5.6 Conversaciones y coaching

Bandeja del agente en el back office (intervención humana). En paralelo, espejo de chats vendedor↔cliente (Kommo) para auditoría cualitativa. Las métricas automáticas de coaching (tiempo de respuesta, ganada/perdida) están en roadmap: no venderlas como producto cerrado.

---

## Qué se puede afirmar en una reunión (y qué no)

**Afirmar con tranquilidad (producto vivo, sujeto a flags del tenant):**

- Pedido por WhatsApp del PdV (texto / audio / foto), con precio de su lista y confirmación.
- Alta de cliente nuevo por recepcionista.
- Vendedor que pasa el pedido de un PdV de su cartera y confirma.
- Consultas y métricas del vendedor en el mismo chat.
- Agenda de plantillas, follow-up, promos, tienda y Field.
- Copilot + embudo del agente en back office.
- Cierre a ERP cuando el tenant tiene la integración prendida.

**Decir como dirección / en curso, no como “ya lo tienen todos”:**

- Módulo Marketing Meta Ads (Click-to-WhatsApp + dashboard de atribución).
- Carga de pedido **dentro** de la app Field (hoy el pedido del vendedor vive sobre todo en WhatsApp; Field es jornada, tareas y consulta).
- Métricas automáticas de coaching sobre chats Kommo.

**No mezclar en el pitch:**

- Un “agente de métricas” separado. Las métricas están en soporte de vendedor (para el preventista) y en Copilot / dashboards (para el supervisor).
- Cuatro números de WhatsApp. Es un número, cuatro roles.

---

## Uso sugerido de este brief

1. Elegir 1 prestación estrella por agente según la reunión (ej. pedido por WhatsApp; pasar pedido en calle; campaña → pedido; Copilot).
2. Apoyar con 2–3 bullets del mismo agente, no saltar de sección.
3. Si hay paseo grabado: recepcionista (número nuevo) → vendedor (armar y confirmar) → soporte (pasar pedido + “¿cómo voy?”) → agenda/campaña → Copilot/embudo.

---

## Nota para la siguiente pasada de diseño

Este archivo prioriza **información y orden comercial**. La otra IA puede mejorar tono, diagramas y piezas visuales; no debería inventar capacidades que no estén arriba. Si una prestación depende de un flag (`copilot_enabled`, `field_app_enabled`, tools opt-in, modo B2C), el pitch tiene que decir “se prende por distribuidora”, no “viene todo de fábrica”.
