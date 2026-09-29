# 085 — Carga de reportes de pedidos sin ERP

**Estado:** Borrador  
**Fecha:** 2026-09-29  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/carga-reportes-pedidos` en backend y backoffice  
**Relaciona:** métricas comerciales (`data_access/comercial_metrics.py`, spec [077](./077-metricas-pareto-y-label-semana.md)). No las cambia. Los pedidos de este módulo entran porque ya cuentan todo `confirmado` o `descargado`, sin filtrar origen.

Un tenant sin sync usable con el ERP puede subir el reporte de ventas que exporta el ERP (días, semanas o meses). Esos pedidos quedan en `{schema}.pedidos` y las métricas de frecuencia y ticket medio los ven igual que a los que llegan por sync.

---

## Objetivo

En Pedidos del backoffice, un usuario sube el archivo del formato que se configuró para su tenant. El sistema valida la forma, procesa en background y deja pedidos nuevos en estado `confirmado`, origen `reporte`. Lo que ya estaba no se duplica ni se actualiza. Las filas que no se pueden cargar vuelven en un CSV para corregir y volver a subir.

### Métricas de éxito

- Un tenant sin parser registrado no ve el botón de carga.
- Un archivo con otra forma se rechaza en el momento y no crea un job.
- Volver a subir tres meses de historial, cuando solo la última semana es nueva, inserta solo esa semana.
- Una línea rota deja el pedido entero afuera. El CSV corregido, al subirlo, inserta ese pedido una sola vez.
- Un pedido cargado por este camino aparece en las métricas comerciales sin cambiar esa pantalla.
- Un SKU creado desde el archivo queda con `en_catalogo = false`. Un SKU que ya estaba publicado sigue publicado.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Qué se construye | El módulo de carga. La pantalla de Métricas no se toca | Frecuencia, ticket y hueco ya se calculan sobre `pedidos` `confirmado` o `descargado`. El hueco de los tenants sin ERP es que no tienen filas, no la fórmula | Rediseñar Métricas alrededor de frecuencia y ticket |
| Parser | Un módulo Python por schema, registrado en código, escrito cuando llega el Excel de ejemplo. No escribe en la base: devuelve pedidos normalizados y filas rotas | Los Excel de ERP cambian de hoja, encabezado y totales al pie. El motor de conectores ya trabaja así | Un mapeo de columnas en configuración: no aguanta celdas combinadas ni varias hojas |
| Motor compartido | Resuelve cliente, producto, deduplicación e insert. El parser no inserta | La regla “el pedido entra completo o no entra” tiene que vivir en un solo lugar. Si cada parser inserta, cada uno la implementa distinto | Cada parser escribe `pedidos` a su manera |
| Formato inválido | `validar_formato` falla → HTTP 400, sin fila de job | El usuario tiene que ver el rechazo al instante, con el archivo todavía en el cuadro | Crear un job fallido para un archivo que ni siquiera es el de ese tenant |
| Filas rotas | Entran las válidas. Las rotas se descargan en CSV con las columnas originales más `motivo`. El mismo parser ignora la columna `motivo` | El usuario corrige y vuelve a subir. No tiene que rearmar el Excel del ERP | Rechazar el archivo entero por una fecha ilegible |
| Pedido atómico | Si cualquier fila de ese pedido está rota, no se inserta ninguna y todas vuelven al CSV | Si se guardara a medias, la recarga chocaría con la clave y la línea corregida no entraría nunca | Saltar la línea mala y guardar el resto cuando la cabecera tiene total |
| Dedup | Clave en `erp_reference_id` con prefijo `reporte:`. Con número de comprobante: `reporte:{comprobante}`. Sin número: `reporte:{clave de cliente}:{fecha}:{importe a 2 decimales}`. Solo inserta. No actualiza | Van a bajar todo el historial y volver a subir la última semana. Hay que reconocer lo ya cargado | Cliente + fecha + importe siempre: dos comprobantes distintos del mismo día y el mismo importe se perderían cuando el archivo sí trae número |
| Pedido borrado | La búsqueda de la clave incluye filas con `deleted_at`. El índice único también | Volver a subir el archivo no revive un pedido que alguien borró | Ignorar borrados: el mismo comprobante volvería a aparecer |
| Duplicado en el mismo archivo | El parser declara si el archivo es de cabeceras o de líneas. En cabeceras, la primera fila de una clave es el pedido y las filas siguientes de esa clave cuentan como “ya estaban”, sin ir al CSV. En líneas, las filas de la misma clave son el detalle de un solo pedido, no duplicados | Una cabecera repetida es el mismo comprobante exportado dos veces. Una línea repetida es otro producto del mismo comprobante | Tratar toda fila repetida como duplicado: se perderían los productos de un archivo de líneas |
| Sin comprobante, archivo de líneas | Todas las líneas del mismo cliente y la misma fecha son un solo pedido. El total es la suma | Sin número no hay cómo separar dos facturas del mismo día | Tratar cada línea como un pedido: infla la frecuencia |
| Cliente | Match exacto por la clave que declara el parser: `codigo`, `cuit` o `nombre` (trim + minúsculas). Sin parecido. Si no existe, se crea. Si hay dos, motivo `cliente ambiguo` y el pedido no entra | Un match por similitud le cargaría el pedido a otro kiosco | `pg_trgm` |
| Alta de cliente | `nombre` y, si viene, `codigo` / `cuit` / `razon_social`. `phone_number = reporte-{clave}` (sanitizado, único). `activo_ai = false`. `is_primary = true`. Lista de precios: la default del tenant, la misma que usa el alta de clientes. `is_mock = false`. No se geocodifica ni se arma `puntos_venta` | `phone_number` es obligatorio y el reporte no trae WhatsApp. Un número inventado que parezca teléfono haría que el agente le escriba. Sin dirección el mapa no tiene qué pintar. Las métricas leen `cliente_id` | Crear el PDV en el mapa con dirección vacía. Dejar `activo_ai = true` |
| Cliente y producto nuevos | Se crean solo si el pedido se inserta | Si el pedido vuelve al CSV, no tiene que quedar un cliente vacío ni un SKU huérfano | Crear el cliente al parsear y dejarlo si después el pedido se rechaza |
| Producto | Líneas solo si el archivo las trae. SKU existente: se usa y no se toca `en_catalogo`. SKU nuevo: se crea con el nombre del archivo y `en_catalogo = false`. El importe queda en la línea, no en una lista de precios | El catálogo es lo que el agente ofrece. El historial igual necesita el SKU para la línea | Publicar el SKU. No crear el producto y perder la línea |
| Vendedor | En un cliente nuevo, se asigna `clients.vendedor` solo si el nombre del archivo coincide con un vendedor existente, uno solo. No se crean vendedores. En un cliente que ya existe no se pisa el vendedor | El reporte no es el alta de la red comercial | Crear el vendedor desde el Excel |
| Estado y origen | `estado = confirmado`, `origen = reporte`, `is_mock = false` | Las métricas cuentan `confirmado` y `descargado` y no filtran origen. `reporte` permite verlos en el filtro de Pedidos | Reusar `origen = erp`: se mezclaría con la sync |
| Fecha | Se persiste el día de calendario del archivo. Si `pedidos.fecha` es `timestamptz`, se guarda ese día a las 12:00 UTC | Medianoche UTC en Argentina cae en el día anterior y correría la frecuencia | Guardar medianoche local o UTC |
| Importe | `Decimal` a 2 lugares. `10.5` y `10.50` son la misma clave | Un float parte la dedup | `float` |
| Total del pedido | El de la cabecera. Si no hay cabecera con total, la suma de las líneas | El ERP a veces trae el total del comprobante y a veces solo el detalle | Sumar siempre las líneas y ignorar el total del comprobante |
| Job | Fila en `public.pedido_reporte_cargas`. Archivo original y CSV de rotas en el bucket privado `pedido-reportes` | El proceso se puede reiniciar. La barra lee la fila, no la memoria del request | `BackgroundTasks` de FastAPI: un deploy mata la carga y no hay de dónde retomarla |
| Worker | El scheduler que ya corre en el backend, cada 15 segundos, una carga a la vez en todo el proceso. Lotes de 200 pedidos por transacción, contra el pool que ya usa la API | Una carga de tres meses no puede abrir otro pool. El límite del proyecto es 60 conexiones. 15 segundos es lo que espera alguien mirando la barra | Un worker nuevo. Procesar en el request |
| Retoma | `procesando` por más de 30 minutos vuelve a `pendiente`. Máximo 3 tomas. A la tercera, `fallida`. Una excepción del parser o del motor pasa directo a `fallida` y no se reintenta | Un deploy a mitad se retoma y la clave evita duplicar. Un archivo que siempre explota no puede reintentarse para siempre | Reintentar sin tope. Dejar `procesando` hasta que alguien lo mire |
| Tope | 80 MB o 500.000 filas. Por encima, 400 y sin job | El export de un año de `del_corro` pesa 50 MB y trae 395.518 filas. 30 MB o 150.000 filas lo rechazarían, y es el archivo que este módulo tiene que aceptar | Sin tope. El tope anterior de 30 MB / 150.000 filas |
| Filas excluidas | El parser puede devolver filas excluidas, aparte de las rotas. No van al CSV de corrección. El job cuenta `filas_excluidas` | Una nota de crédito no es una fila para arreglar. Si va al CSV, el usuario la corrige y la vuelve a subir, y la frecuencia queda mal | Meter NCA/NCB en el CSV de rotas |
| Cantidad 0 | Esa línea se tira y el pedido sigue con el resto. Si no queda ninguna línea con cantidad, el pedido no entra y esas filas van al CSV con motivo `cantidad_cero` | En `del_corro`, 161 comprobantes de venta tienen una línea en cero y otras con cantidad. Rechazar el comprobante entero perdería la venta | La regla atómica aplicada a cantidad 0 |
| Dedup histórica | Además de `erp_reference_id`, si `sync_metadata->>'comprobante'` es igual al comprobante, cuenta como ya estaba | `del_corro` ya tiene 16.923 pedidos cargados a mano con el comprobante en `sync_metadata` y sin clave `reporte:` | Solo mirar `erp_reference_id`: re-subir el Excel de 2026 duplicaría el historial |
| Una carga por tenant | Mientras haya una `pendiente` o `procesando` de ese schema, la siguiente responde 409 | Dos archivos a la vez se pisarían la dedup | Encolar varias y procesarlas en serie sin avisarle al usuario |
| Convivencia con ERP | Si el tenant tiene sync de pedidos ERP activa, el endpoint rechaza y el botón no se muestra | Los dos caminos escribirían el mismo historial | Dejar subir igual y deduplicar contra ids del ERP, que no comparten formato |
| Aviso | Barra en Pedidos hasta que el usuario la cierra. Al volver a la pantalla, se lee el último job. Sin mail ni WhatsApp | Es la notificación. El resultado queda además en las últimas cinco cargas | Un mail por carga |
| Parser de `demo` | Este PR registra un parser solo para el schema `demo`, con un xlsx chico de fixture | Sin un parser no se puede probar la pantalla. Los parsers reales llegan en PRs aparte, cuando la implementación tenga el Excel | Esperar al primer tenant real para mergear el motor |
| Mixpanel | Sin evento nuevo | No es un evento de negocio de la taxonomía 073 | Trackear `reporte_cargado` en el browser |

Ejemplo de clave: comprobante `A-0001` → `reporte:A-0001`. Sin comprobante, cliente `ACME`, 2026-09-01, $10.50 → `reporte:acme:2026-09-01:10.50`. La clave de cliente la normaliza el parser (trim + minúsculas en el nombre; el código se guarda como viene, sin espacios extremos).

---

## Alcance explícito

### Incluido (v1)

- Registro de parsers por schema. Contrato: `etiqueta`, `validar_formato`, `parsear`.
- Parser de ejemplo del schema `demo` y fixture.
- Tabla `public.pedido_reporte_cargas`, índice único parcial de una carga activa por schema, índice único en `{schema}.pedidos (erp_reference_id)` para valores `reporte:%` (incluye borrados).
- Bucket privado `pedido-reportes`. Paths `{schema}/{carga_id}/original` y `{schema}/{carga_id}/filas-rotas.csv`. El CSV va en UTF-8 con BOM para que Excel abra los acentos.
- Endpoints del tenant: si está habilitado, subir, leer la carga, listar las últimas cinco, bajar el CSV de rotas.
- Worker en el scheduler existente.
- Alta de cliente y de producto con las reglas de la tabla de arriba.
- Pedidos `confirmado` / `reporte`. Líneas en `items_pedido` cuando el archivo las trae. Si `pedidos.items` existe, se llena con el detalle o con `[]`.
- En Pedidos: botón **Cargar reporte** (solo con parser y sin sync de pedidos ERP), cuadro con la etiqueta del formato, barra de progreso y resultado, descarga del CSV, últimas cinco cargas, filtro de origen **Reporte**.
- Motivos de fila que el motor agrega: `sin cliente`, `cliente ambiguo`, `fecha ilegible`, `sin importe`, `sin lista de precios por defecto`, `telefono sintetico duplicado`. El parser puede agregar otros, en el mismo CSV.

### Fuera de alcance

- Cambiar la pantalla de Métricas, la fórmula de frecuencia o el monto en riesgo.
- El parser de `del_corro` en el mismo PR que el motor. Las reglas están en la sección de prueba real. El código entra en el PR siguiente, cuando el motor ya está mergeado. No se insertan los 63.467 comprobantes de este Excel en ese PR: primero corre en seco.
- Editor de mapeo de columnas en el backoffice.
- Actualizar un pedido ya cargado (importes, líneas, cliente).
- Crear vendedores, zonas, direcciones o puntos en el mapa.
- Publicar en catálogo los SKU nuevos. Cargarles precio de lista.
- Mail, WhatsApp o push cuando termina la carga.
- Correr este módulo en un tenant con sync de pedidos ERP activa.
- Eventos de Mixpanel.

---

## Contrato del parser

```text
etiqueta: str                     # lo que ve el usuario, ej. "Ventas .xlsx, hoja Ventas"
validar_formato(nombre, bytes) -> str | None    # None = ok; texto = rechazo, sin job
parsear(bytes) -> ParseResult
```

`ParseResult` trae pedidos, filas rotas y filas excluidas. Las excluidas no van al CSV. Cada pedido trae:

- `clave_cliente`, `match_por` (`codigo` | `cuit` | `nombre`)
- datos para el alta: nombre, y si vienen código, CUIT, razón social, nombre de vendedor
- `comprobante` o vacío
- `fecha` o el motivo si no se pudo leer
- `total` de cabecera o vacío
- líneas: SKU, nombre, cantidad, precio unitario
- las filas de origen (columnas originales y número de fila) para poder devolverlas en el CSV

Una fila que el parser no puede leer sale en `filas_rotas` con `motivo` y no forma un pedido. El motor puede rechazar después un pedido que el parser dio por bueno (cliente ambiguo, sin lista default) y entonces manda al CSV todas las filas de origen de ese pedido.

---

## Contrato HTTP

Header de tenant: `x-schema-name`, como el resto de la API.

| Método | Uso | Respuesta |
|--------|-----|-----------|
| `GET /{schema}/pedidos/reportes/habilitacion` | ¿Hay parser y no hay sync de pedidos ERP? | `{ habilitado, etiqueta }` |
| `POST /{schema}/pedidos/reportes` | Multipart con el archivo | 202 + carga `pendiente`. 400 si el formato no coincide o se pasa el tope. 403 si no hay parser o hay sync de pedidos ERP. 409 si ese schema ya tiene una carga `pendiente` o `procesando` |
| `GET /{schema}/pedidos/reportes` | Últimas cinco | Lista con contadores y si hay CSV |
| `GET /{schema}/pedidos/reportes/{id}` | Estado para la barra | La fila |
| `GET /{schema}/pedidos/reportes/{id}/filas-rotas` | Descarga | El CSV, o 404 si esa carga no tuvo rotas |

Contadores al terminar: `pedidos_nuevos`, `pedidos_ya_estaban`, `filas_rotas`, `filas_excluidas`. La barra muestra las excluidas como “no se cargan” (notas de crédito y tipos que el parser descarta). No hay botón de descarga para esas.

Estados: `pendiente`, `procesando`, `listo`, `fallida`. En la barra, `pendiente` y `procesando` se muestran como “Procesando reporte…”.

`sync_metadata` del pedido: `{"source": "pedido_reporte", "carga_id": "<uuid>"}`.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/carga-reportes-pedidos` | Migración, bucket, motor, worker, endpoints, parser `demo`, tests |
| 2 | `product-management-app` | `feat/carga-reportes-pedidos` | Botón, cuadro, barra, últimas cinco, filtro Reporte |

El backoffice no se mergea antes: sin los endpoints el botón no tiene a quién llamar. El parser de `del_corro` es un tercer PR, con las reglas de la prueba real de abajo. Ese PR no inserta el Excel de un año: lo corre en seco y deja el resumen.

---

## Prueba real — `del_corro`

Archivo: `Detalles de comprobantes 9-24 al 8-25.xlsx`. Una hoja, 395.518 filas, del 2024-09-02 al 2025-08-30. Cada fila es un producto. El pedido es el `Comprobante`.

Columnas que usa el parser: `Cliente` (código), `Razon_Social`, `Fecha`, `Comprobante`, `Art`, `articulo`, `Cantidad`, `neto`. `cod_ven` es un número de vendedor del ERP. En `del_corro.vendedores` no hay esa clave, así que el parser no asigna vendedor y no rechaza la fila por eso.

| Qué | Número |
|-----|--------|
| Comprobantes | 70.292 |
| De venta (FAA, FAB, PEX, NPX, NPA, NPB), con alguna cantidad distinta de cero | 63.467 |
| Notas de crédito y otros (NCA, NCB, NCX, DEX, NDB) | se excluyen, no van al CSV |
| Cliente ya existe (`clients.codigo`) | 54.604 pedidos |
| Cliente a crear | 8.863 pedidos, 469 códigos distintos. Teléfono `reporte-{codigo}`, `activo_ai = false` |
| SKU a crear, `en_catalogo = false` | 275 códigos, 20.756 líneas |
| Mismo cliente y mismo día con más de un comprobante de venta | 9.783 días |

El precio de la línea es `neto` por `Cantidad`. `Importe` es el bruto (en la muestra, 2975,62 neto y 3600,50 importe). El historial que ya está cargado usó `neto`. Usar `Importe` inflaría el ticket medio contra esos pedidos.

En la base, `del_corro.pedidos` va del 2025-11-06 al 2026-09-28 (17.103 vivos). Este Excel termina el 2025-08-30, así que no pisa esas fechas. Igual la dedup mira `sync_metadata.comprobante`, porque el lote de junio–septiembre 2026 se cargó así y no tiene clave `reporte:`.

Agrupar por cliente y fecha juntaría esas 9.783 jornadas de más de un comprobante y bajaría la frecuencia, que es la métrica que este módulo tiene que alimentar. La clave es `reporte:{Comprobante}`.

El parser de `del_corro` rechaza el archivo si faltan las columnas de arriba o si la hoja no es la primera. No inserta este Excel hasta que el corrido en seco coincida con esta tabla.

---

## Migración de base de datos

Tabla nueva `public.pedido_reporte_cargas`:

- `id` uuid PK
- `schema_name` text
- `estado` text (`pendiente`, `procesando`, `listo`, `fallida`)
- `etiqueta` text
- `archivo_path` text, `archivo_nombre` text
- `filas_rotas_path` text null
- `pedidos_nuevos` int, `pedidos_ya_estaban` int, `filas_rotas` int, `filas_excluidas` int
- `error_mensaje` text null
- `intentos` int default 0
- `creado_por` text null (id de usuario del backoffice, sin email)
- `created_at`, `started_at`, `finished_at`

Índice `(schema_name, created_at desc)`. Único parcial: una fila por schema con estado `pendiente` o `procesando`.

En cada schema de `distribuidoras`: índice único `pedidos (erp_reference_id) WHERE erp_reference_id LIKE 'reporte:%'`.

Bucket privado `pedido-reportes` en el proyecto Suplai-east (`cvlbietibaaehgeimxgw`). No es DDL de SQL: se crea en Storage al desplegar el backend. Si el bucket no está, la carga queda `fallida` con mensaje, no a medias.

Sin backfill. Los pedidos que ya existan no se tocan.

Rollback: sacar el worker y los endpoints. La tabla y el bucket pueden quedar. No borrar `pedidos` cargados: ya son historial del tenant. Quitar el índice único solo si no quedó ninguna clave `reporte:%`.

---

## Plan de prueba en CI/CD

Pytest en `backend-supabase`, en el PR del backend. El backoffice no agrega tests de UI en este PR: la pantalla se verifica con el plan humano. Checks que ya existen del backend tienen que seguir verdes.

Casos:

- Formato distinto, archivo de más de 80 MB o de más de 500.000 filas: 400, cero filas en `pedido_reporte_cargas`.
- Una línea con cantidad 0 no saca el pedido si hay otra línea con cantidad. Un comprobante cuyas líneas están todas en cero no se inserta y esas filas van al CSV con `cantidad_cero`.
- Una fila que el parser marca excluida (nota de crédito) suma `filas_excluidas` y no aparece en el CSV.
- Un pedido viejo con `sync_metadata.comprobante` igual al comprobante, y sin `erp_reference_id`, cuenta como ya estaba.
- Segunda subida del mismo schema con una carga `pendiente`: 409.
- Sin parser, o con sync de pedidos ERP activa: `habilitacion.habilitado = false` y el POST responde 403.
- Con comprobante, la segunda corrida no inserta y suma `pedidos_ya_estaban`. Sin comprobante, cliente + fecha + importe tampoco. En un archivo de cabeceras, dos filas con la misma clave cuentan una sola y la segunda suma “ya estaban”. En un archivo de líneas, dos filas con la misma clave y distinto SKU son un pedido con dos líneas.
- Una línea rota: cero inserts de ese pedido, todas sus filas en el CSV con `motivo`. Procesar ese CSV (columna `motivo` ignorada, línea corregida) inserta una vez.
- Cliente nuevo: `phone_number` `reporte-…`, `activo_ai = false`, `en_catalogo` no aplica. SKU nuevo: `en_catalogo = false`. SKU ya publicado: sigue `true`.
- Si el pedido no se inserta, no aparece el cliente ni el producto que solo ese pedido hubiera creado.
- Archivo solo cabecera: pedido sin filas en `items_pedido`, `estado = confirmado`.
- Fecha `2026-09-01` queda en ese día de calendario (12:00 UTC si la columna es `timestamptz`).
- Pedido con `deleted_at` y la misma clave: la recarga no inserta otro.
- Excepción del parser o del motor: `fallida` en esa toma, sin más reintentos. Cada toma suma `intentos` al empezar. Si el proceso muere, a los 30 minutos: con `intentos` menor a 3 vuelve a `pendiente` y la toma siguiente no duplica; con `intentos` en 3 queda `fallida`.
- El query de métricas comerciales, sobre un pedido `origen = reporte` y `estado = confirmado`, lo incluye. No hace falta cambiar el SQL: el test fija que el filtro de estado no excluye este origen.

---

## Plan de prueba humana (antes del PR)

Servicios:

- Backend en `8000`.
- Backoffice en `3000` (`BACKEND_URL=http://localhost:8000`).

Tenant: `demo`, que es el único schema con parser en este PR. Usuario de backoffice de ese tenant.

1. Confirmar que en otro tenant sin parser el botón **Cargar reporte** no está.
2. En `demo`, abrir Pedidos. El botón está. El cuadro dice la etiqueta del parser de ejemplo.
3. Subir un archivo que no sea ese formato. El cuadro muestra el rechazo y la tabla no cambia.
4. Subir el fixture. La barra pasa a “Procesando reporte…”. Al terminar: pedidos nuevos > 0, ya estaban = 0, filas rotas = 0. En el filtro **Reporte** se ven esos pedidos, estado confirmado.
5. Subir el mismo archivo otra vez. Nuevos = 0, ya estaban = los de antes. La tabla no crece.
6. Subir el fixture alterado con una fecha rota en un pedido de varias líneas. Ese pedido no aparece. La barra ofrece el CSV. Abrirlo en Excel: están las filas de ese pedido y la columna `motivo`.
7. Corregir la fecha en ese CSV y volver a subirlo. El pedido entra una vez. Una tercera subida del mismo CSV lo cuenta como ya estaba.
8. En Métricas, el rango que incluye la fecha del fixture muestra facturación de ese cliente. No hace falta buscar una pantalla nueva.
9. En Productos, el SKU nuevo del fixture está en Bajas (`en_catalogo = false`), no en En catálogo.
10. El cliente nuevo no tiene un teléfono de WhatsApp. En la ficha, el agente no queda activo.

OK: los pasos 4, 5, 7 y 8. El 8 es el que justifica el módulo.
