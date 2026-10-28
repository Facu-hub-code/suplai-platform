# 135 — Backoffice agéntico

**Estado:** Borrador.
**Fecha:** 2026-10-27
**Repos:** `product-management-app` (pantallas y proxy), `backend-supabase` (endpoints REST `/{schema}/agentes/*` y stream).
**Rama sugerida:** `feat/backoffice-agentico` en los dos repos.
**Relaciona:** [134](./134-mvp-equipo-de-agentes.md) (índice), [136](./136-agentes-modelo-de-datos.md) (entidades), [137](./137-agentes-eventos-webhooks-scheduler.md) (eventos que actualizan la pantalla), [139](./139-agentes-tools-mcp.md) (`abrir_backoffice`, MCP App compacta).

---

## Objetivo

Que el humano vea y controle al equipo de agentes desde la web: qué encargó, cómo va cada bot, qué le preguntan, qué le proponen y qué le avisaron. Claude puede consultar todo esto; cuando hace falta decidir o ver en detalle, manda el link a la pantalla.

### Criterios de aceptación

- Existen las cinco pantallas (Trabajos, Reportes, Bandeja, Equipo, Avisos) bajo `/agentes`, con su propio menú.
- Trabajos muestra la traza en carriles, un carril por miembro del equipo con el humano incluido, y se actualiza sola cuando un bot registra un paso. Sin recargar y sin que el navegador pregunte cada N segundos.
- Cada paso de la traza se abre y muestra la línea, el estado, las horas y el link a los datos que usó.
- Desde un trabajo en curso el humano puede cancelar y aportar contexto.
- El certificado de un bot se edita solo desde el formulario de Equipo. Guardar crea una versión nueva con motivo obligatorio.
- Un link que manda Claude (`abrir_backoffice`) abre la pantalla y el objeto exactos, y si no hay sesión pasa por login y vuelve.
- Solo los perfiles `owner`, `admin` y `super_admin` del tenant entran a `/agentes`.

---

## Dónde vive

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| App | Segmento `app/agentes/` dentro de `product-management-app`, con layout y menú propios | Reutiliza login, `auth-context`, proxy, Mixpanel y componentes. Para el usuario es otra sección, distinta del backoffice operativo | Repo y deploy nuevos: duplica auth y sesión en un MVP de un solo usuario |
| Navegación | Rutas reales (`/agentes/trabajos/[id]`), no estado dentro de `app/page.tsx` | Los links de Claude tienen que abrir un objeto exacto | Seguir el patrón de secciones con `useState` de la home |
| Datos | Proxy `app/api/agentes/*` → backend `/{schema}/agentes/*` con `x-schema-name` | Es la regla del workspace: el backoffice no toca la base | Leer Supabase directo |
| Tiempo real | Server-Sent Events: `GET /{schema}/agentes/trabajos/{id}/stream` | Cada `trabajo.paso` empuja el evento a la pantalla abierta (principio 3) | Refetch cada 5 s |
| Componentes | shadcn/ui del repo (`components/ui/`) y `lucide-react` | Mismo look que el backoffice | Una librería de timeline externa |

La entrada al backoffice agéntico es un ítem «Agentes» en el menú del backoffice operativo, visible solo para los perfiles con permiso y si el tenant tiene `metadata.agentes.habilitado`.

---

## Rutas

| Ruta | Pantalla |
|------|----------|
| `/agentes` | Redirige a `/agentes/trabajos` |
| `/agentes/trabajos` | Lista de trabajos |
| `/agentes/trabajos/[id]` | Detalle con la traza en carriles |
| `/agentes/trabajos/[id]?paso=[evento_id]` | Detalle con un paso abierto |
| `/agentes/reportes` y `/agentes/reportes/[id]` | Lista y vista de un reporte |
| `/agentes/bandeja` y `/agentes/bandeja/[tipo]/[id]` | Preguntas y propuestas; `tipo` es `pregunta` o `propuesta` |
| `/agentes/equipo` y `/agentes/equipo/[bot_id]` | Bots y su certificado |
| `/agentes/equipo/[bot_id]/certificado` | Formulario de edición |
| `/agentes/avisos` | Traza de avisos y preferencias de banda |

Todas aceptan `?schema=` para un super_admin que mira otro tenant, como el resto del backoffice.

---

## Pantalla Trabajos

Es la más importante del MVP.

### Lista

Tabla con: pedido en lenguaje natural (recortado), estado, bots delegados (avatares), avance, pregunta abierta (sí/no), creado, terminado y link al reporte. Filtros por estado y por fecha. Orden por creado, más nuevo arriba.

El avance es `pasos terminados / pasos planificados`. Los pasos planificados salen del evento de tipo `plan` del jefe de cuenta. Si todavía no hay plan, se muestra «Armando el plan».

### Detalle: la traza en carriles

```text
              ─────────── tiempo ───────────▶
Faka (humano) │ ● encargo                         ◆ respondió        │
Jefe de cuenta│   ● plan ── ● reparte                      ● consolida ● fin
Analista vtas │            ● exporta ── ● calcula ── ? pregunta ── ● hallazgo
```

- Un carril por actor del trabajo: humano asignado primero, después el jefe de cuenta, después los demás bots en el orden en que se sumaron.
- Cada paso es una marca en su carril, en orden de inicio de izquierda a derecha. Los pasos con inicio y fin se dibujan como barra; los instantáneos como punto.
- Color por estado, con la guía de Linear: `pensando` (gris animado), `ejecutando` (azul animado), `esperando` (ámbar), `terminado` (verde), y error (rojo) para el tipo `error`. El color nunca es la única señal: cada estado tiene ícono y texto.
- Forma por tipo: `plan` (rombo), `paso` (punto o barra), `hallazgo` (estrella), `pregunta` (signo de pregunta), `error` (cruz), `fin` (bandera).
- Arriba, una franja con el estado del trabajo y, si hay pregunta abierta, la pregunta con el botón «Responder».
- En mobile los carriles pasan a una lista vertical por actor, con el paso actual primero.

Al abrir un paso se ve un panel lateral con: línea en lenguaje humano, actor, tipo, estado, inicio, fin, duración, run asociado y el link a los datos en el bucket (se pide un link firmado al abrirlo, ver [141](./141-agentes-reportes.md)).

### Acciones

| Acción | Cuándo | Qué llama |
|--------|--------|-----------|
| Aportar contexto | Trabajo en `en_curso` o `esperando_humano` | `POST /agentes/trabajos/{id}/contexto` → emite `contexto.aportado` |
| Responder pregunta | Pregunta abierta | `POST /agentes/preguntas/{id}/respuesta` |
| Cancelar | Trabajo no terminado | `POST /agentes/trabajos/{id}/cancelar` → el adaptador cancela los runs vivos |

Cancelar pide confirmación. El contexto aportado aparece al instante en el carril del humano.

---

## Pantalla Reportes

Lista de reportes terminados: título, trabajo, resumen de dos líneas y fecha. La vista de un reporte embebe la página web del bucket en un iframe con link firmado recién pedido, con los botones «Descargar PDF» y «Copiar link para compartir». El link para compartir es el de `/agentes/reportes/[id]`, no el firmado: el firmado vence y el de la pantalla siempre pide uno nuevo.

---

## Pantalla Bandeja

Dos pestañas, con contador cada una.

**Preguntas.** Texto de la pregunta, bot que la hizo, trabajo, banda de aviso y antigüedad. Responder abre un textarea; se puede marcar «Guardar como regla para la próxima», que crea un Contexto con alcance `candidato_regla` (ver [136](./136-agentes-modelo-de-datos.md)).

**Propuestas.** Acción pedida en lenguaje humano, bot, motivo del bot, efecto (antes y después, del borrador) y riesgo. Botones «Aprobar» y «Rechazar»; rechazar pide motivo. La decisión llama a `POST /agentes/propuestas/{id}/decision`, que resuelve el borrador del 132 y emite el evento correspondiente.

---

## Pantalla Equipo

Tarjeta por bot: nombre, rol, estado (activo o pausado), certificado vigente (versión y fecha), último run y consumo estimado del mes.

| Acción | Qué hace |
|--------|----------|
| Pausar o reanudar | Cambia `bot.estado`. Un bot pausado no recibe eventos nuevos; sus runs vivos se cancelan |
| Editar certificado | Abre el formulario |
| Ver historial | Versiones del certificado con quién, cuándo, motivo y diff contra la anterior |

### Formulario del certificado

Campos del [136](./136-agentes-modelo-de-datos.md): qué hace (texto), fuentes (checkboxes de familias de datos), nivel por tarea (select L1–L5 por cada tarea del rol) y reglas (lista de textos). Motivo del cambio obligatorio. El select no deja subir de L3 una tarea marcada `toca_cliente_final` (fuera del MVP). Guardar crea la versión `n+1`; nunca pisa.

Es la única forma de editar un certificado (principio 9).

---

## Pantalla Avisos

**Traza.** Tabla de avisos: qué (objeto de origen con link), destinatario, canal, banda, enviado, leído y respuesta. Filtro por banda y por canal.

**Preferencias.** Por tipo de aviso (pregunta, propuesta, reporte listo, error de trabajo), la banda: inmediato, lote diario o resumen semanal. Defaults: reporte listo y error inmediato; pregunta inmediato; propuesta en lote diario. En el MVP el único canal es el correo.

---

## Endpoints del backend que usa

Todos bajo `/{schema}/agentes/`, con el JWT del backoffice y el chequeo de perfil.

| Método | Ruta | Para |
|--------|------|------|
| GET | `trabajos`, `trabajos/{id}` | Lista y detalle con actores, runs y eventos de traza |
| GET | `trabajos/{id}/stream` | SSE con eventos `traza`, `estado`, `pregunta` |
| POST | `trabajos/{id}/contexto`, `trabajos/{id}/cancelar` | Acciones del humano |
| GET | `reportes`, `reportes/{id}` | Con links firmados recién pedidos |
| GET | `preguntas`, `propuestas` | Bandeja |
| POST | `preguntas/{id}/respuesta`, `propuestas/{id}/decision` | Bandeja |
| GET/POST | `bots`, `bots/{id}/estado`, `bots/{id}/token` | Equipo |
| GET/POST | `bots/{id}/certificados` | Historial y versión nueva |
| GET | `datos/firmar?path=` | Link firmado a un archivo del bucket del tenant |
| GET/PUT | `avisos`, `avisos/preferencias` | Avisos |

La lógica vive en `services/agentes_*` del backend; los routers solo traducen HTTP. Las tools MCP del 139 llaman a los mismos servicios.

---

## Analítica

Eventos Mixpanel nuevos (cliente, `lib/analytics.ts`), a sumar al spec 073: `agentes_trabajo_abierto`, `agentes_paso_abierto`, `agentes_contexto_aportado`, `agentes_pregunta_respondida`, `agentes_propuesta_decidida`, `agentes_certificado_guardado`. Propiedades: `trabajo_id`, `bot_rol`, `origen` (`link_claude` o `navegacion`). El origen sale de `?src=claude`, que agrega `abrir_backoffice`. Sirve para el criterio «el humano entiende el avance sin preguntar».

---

## Fuera de alcance

- Más de un rol humano, permisos finos por pantalla.
- Edición de prompts de los bots desde la web (el prompt es producto, ver [140](./140-agentes-bots-mvp.md)).
- Canales de aviso distintos del correo.

## Plan de prueba

- Unit: el componente de carriles ordena actores y pasos, y dibuja cada combinación tipo × estado.
- E2E con datos sembrados: lista, detalle, abrir paso, aportar contexto y verlo aparecer por SSE.
- Permisos: un perfil `vendedor` recibe 403 en `/agentes` y en el proxy.
- Certificado: guardar dos veces deja dos versiones y el historial muestra el diff.
- Link de Claude sin sesión: login y vuelta al objeto.
