# P2 · Check final (DEV-163) — borrador actualizado del 2026-11-02 (22:40 UTC)

**Estado:** borrador para cerrar el proyecto cuando respondan las distribuidoras. Cada punto lleva la evidencia que dejaron los comentarios de Linear; lo que era de solo lectura se repitió hoy a las 22:39 UTC con el MCP de Supabase (`cvlbietibaaehgeimxgw`) y `curl`. Esta revisión no escribió nada en producción.

Leyenda: ✅ verificado · ❌ no cumple · ⏳ pendiente (la issue o el tercero entre paréntesis lo cierra) · ➖ fuera de alcance por decisión

## Resumen por punto

| # | Punto | Estado | Evidencia / lo que falta | Lo cierra |
|---|---|---|---|---|
| 1.1 | 3 fallas simuladas en gonzales (ERP caído, credenciales inválidas, respuesta vacía) | ⏳ | #421 mergeado (Edge Function `erp-mock`, runbook, tests). Falta desplegar `erp-mock` y correr las 3 fallas en una ventana acordada; hace falta un partner de prueba de GEV en gonzales. DEV-156 está En curso | DEV-156 |
| 1.2 | Reenvío DEV-82 y O5 en gonzales | ⏳ | Sin prueba en gonzales. Sí hay un O5 real en dimer: el pedido 37012 salió solo a Odoo (ver Trabajo adicional, DEV-168) | DEV-156 / DEV-157 |
| 1.3 | Altas en almaro y DEV-83 con tokens reales | ⏳ | Runbook listo en el comentario de DEV-157 (3 casos de alta, `buscar_incidencias` según tipo de token; 10 tests pasan). Nada corrido: faltan 5 teléfonos de prueba y los dos tokens. Issue en Backlog | DEV-157 |
| 2.1 | Chequeo diario: 7 corridas sin falsos positivos | ⏳ | 1 de 7. Única corrida hasta hoy: manual, 02/11 10:36 AR, con 0 falsos positivos y 0 umbrales cambiados. La primera programada es el 03/11 07:00; las 7 seguidas terminan el 09/11 | DEV-158 |
| 2.2 | Alerta externa si el worker se cae | ✅ | Probado en prod el 02/11 22:30 UTC: mail "Worker de Suplai caído" y mail "recuperado" recibidos. Ver evidencia 2.2. No se cortó el proceso físico | DEV-143 (Done) |
| 3.1 | Espejo de precios sin filas viejas | ✅ | Ver evidencia 3.1 | DEV-159 (Done) |
| 3.2 | gonzales: octubre 2025 resuelto o descartado; mayo–agosto 2026 confirmados | ⏳ | #419 mergeado. Oct 2025 murió por timeout (GEV tarda 49,5 s en 01–03/10; el límite era 30 s). May–ago 2026: GEV responde 404 "No se encontraron registros", no es bug. Faltan dos decisiones (ver Pendiente de terceros) | DEV-150 (Done en Linear, decisión abierta) |
| 3.3 | Las C7 de dimer tienen todas una decisión | ⏳ | De 32 abiertas: 23 vinculadas (02/11 16:05–16:15 UTC), 2 `ignorada` (clientes 167 y 296). **Quedan 7 abiertas**, confirmado hoy en `core.erp_incidencias`: 360, 446, 676 (confianza media) y 376, 636, 1346, 1533 (preguntas a dimer). Issue en Backlog | DEV-160 |
| 3.4 | el_gigante 1682 confirmado/desvinculado; dimer 7157 y 7166 con sus pedidos en Odoo | ⏳ | Depende de terceros. Hoy siguen en `pendiente_vinculo` los pedidos 32468, 36413 y 32588 de dimer. Issue en Todo, sin comentarios | DEV-161 |
| 4.1 | Webhook de Slack rotado y logs sin credenciales | ➖ | Decisión del orquestador (02/11): el canal de Slack no se usa y DEV-151 se canceló. Las alertas van por mail. Lo hecho: #414 enmascara las URLs con credenciales en los logs (desplegado en backend, worker y MCP). La revisión de logs de Railway no se repitió hoy | decisión |
| 4.2 | Request sin credenciales a `/{schema}/erp/*` responde 401 | ✅ | `curl` repetido hoy: 401 en dimer, gonzales y almaro. Backoffice de prod con sesión real: carga. Ver evidencia 4.2 | DEV-162 (Done) |
| 5 | cordoba_frost y rawson afuera, con el motivo | ✅ (con cambio) | cordoba_frost sigue en pausa: credenciales de Cianbox vencidas. **rawson queda dentro del monitoreo "desde el 02/11, por decisión"**: sincroniza productos, listas y precios cada 6 h. Ver evidencia 5 | decisión de Faka |
| 6 | Spec "Reglas de integración ERP" actualizada; status update y cierre del proyecto | ⏳ | Spec ✅: editada el 02/11 22:20 UTC (comentario de DEV-163). Faltan el status update y el cierre del proyecto, que van cuando respondan las distribuidoras | DEV-163 |

## Evidencia

### 2.2 Alerta del worker — ✅

Probado en prod el 02/11 ~22:30 UTC con `railway ssh` al contenedor del backend, sin apagar el worker (los pedidos se mandan desde ahí, y volver a levantarlo desde el MCP de Railway lo arranca como API):

1. `revisar()` real: ok, latido de hace 24 s.
2. `revisar()` con el reloj adelantado 16 min: "el worker no late hace 16 min". `avisar()` logueó `WORKER_CAIDO` y dejó la clave de alerta en Redis.
3. Mail "[production] Worker de Suplai caído" recibido en facundo@suplaisales.com, desde no-reply@suplaisales.com.
4. Minutos después el vigía real de la API vio el latido al día, borró la clave (22:32 UTC) y mandó "[production] Worker de Suplai recuperado", que también llegó.

Quedan probados la detección, Redis, la deduplicación, Brevo y la recuperación. **No se probó el corte físico del proceso**, que solo frena el latido. También quedó documentado el caso real del 02/11 (un redeploy hecho por la API de Railway arrancó el worker como API, con 132 jobs pendientes) que el vigía debe cubrir. Config: `WORKER_VIGIA_ENABLED=true`, `/health/worker` → 200; #417 y #420 mergeados.

### 3.1 Espejo de precios sin filas viejas — ✅

Se compara `count(*)` de `{schema}.erp_prices_raw` con `core.erp_sync_conteos` (paso `precios`), y se cuenta cuántas filas tienen `synced_at` anterior a la última corrida menos 1 h (sería una fila que el ERP ya no devolvió).

```sql
select filas, actualizado_at from core.erp_sync_conteos where paso = 'precios' order by schema_name;
select count(*), max(synced_at), min(synced_at),
       count(*) filter (where synced_at < (select actualizado_at from core.erp_sync_conteos c
                                           where c.schema_name = '<schema>' and c.paso = 'precios') - interval '1 hour') as viejas
from <schema>.erp_prices_raw;
```

| Tenant | `erp_prices_raw` | `erp_sync_conteos.filas` | Coincide | Filas viejas | Último `synced_at` |
|---|---|---|---|---|---|
| almaro | 52.810 | 52.810 | sí | 0 | 02/11 18:00 UTC |
| benfresh | 354 | 354 | sí | 0 | 02/11 18:00 |
| dimer | 5.039 | 5.039 | sí | 0 | 02/11 22:12 (sync adelantado) |
| el_gigante | 2.233 | 2.233 | sí | 0 | 02/11 18:02 |
| gonzales | 42.792 | 42.792 | sí | 0 | 02/11 18:03 |
| rawson | 599 | 599 | sí | 0 | 02/11 18:03 |

Esta tabla viene del borrador de las 20:50 UTC. Hoy, a las 22:39, se volvió a leer `core.erp_sync_conteos`: los conteos coinciden con la tabla (dimer con la corrida de las 22:12). La corrida de las 18:00 UTC es posterior al deploy de #416 (15:41 UTC), así que la poda ya corrió: la vista previa de DEV-159 anticipaba 400 filas a podar en dimer y no queda ninguna vieja.

Notas:
* `abmauri` tiene la tabla vacía y no tiene conteo. `cordoba_frost` y `del_corro` no tienen fila en `erp_sync_conteos`: cordoba_frost está en pausa (punto 5) y del_corro carga por archivo (`SIN_API`).
* Listas de precio (DEV-165, #423): en dimer, `erp_price_lists_raw` tiene **45 activas y 2 inactivas** (las dos "Predeterminado"), repetido hoy en solo lectura y coincide con lo que anotó la issue tras el sync de las 22:12 UTC. GESCOM no se poda.
* El check prueba que el espejo no tiene sobrantes; no cruza contra lo que Odoo devuelve en vivo.

### 4.2 Sin credenciales responde 401 — ✅

```bash
curl -s -o /dev/null -w '%{http_code}' https://web-production-f544f.up.railway.app/{schema}/erp/config
curl -s -o /dev/null -w '%{http_code}' https://web-production-f544f.up.railway.app/{schema}/erp/dependency-health
```

| Schema | `/erp/config` | `/erp/dependency-health` |
|---|---|---|
| dimer | 401 | 401 |
| gonzales | 401 | 401 |
| almaro | 401 | 401 |

Repetido el 02/11 22:39 UTC. DEV-162 también anotó 401 en `/gonzales/erp/prices-diff` y `bridge-config` protegido por `X-ERP-Ingest-Token`. **Sesión real:** el backoffice de prod (app.suplaisales.com, usuario de almaro, rol supervisor, 22:35 UTC) cargó Configuración → Integraciones ERP completa por los proxies autenticados: conexión GEV y capacidades, estado de integración (listas 17/16, productos 3405/3327, clientes 427/2740, pedidos 228/2453) y los pasos 1 a 6. El resto de los endpoints de `/{schema}/erp/*` no se probó uno por uno.

### 5 Límite: cordoba_frost y rawson — ✅ con cambio de alcance

```sql
select d.schema_name, c.connector, c.last_sync_at, c.push_orders_enabled, c.orders_last_sync_at
from core.erp_connector_configs c join public.distribuidoras d on d.id = c.tenant_id
where d.schema_name in ('cordoba_frost','rawson');
```

| Tenant | Conector | `last_sync_at` | Estado / motivo |
|---|---|---|---|
| cordoba_frost | Cianbox | 06/10 18:02 | En pausa. Credenciales vencidas: `Cianbox auth rejected: Usuario o contraseña inválidos` (O12 abierta desde el 29/10, pedidos con el error desde el 07/10). Hoy tiene 3 incidencias de salud abiertas, consecuencia de eso. Mails silenciados con `SALUD_ERP_TENANTS_SIN_MAIL=cordoba_frost` (DEV-154) |
| rawson | Sistel | **02/11 13:28 UTC** (releído hoy) | **Dentro del monitoreo desde el 02/11, por decisión del orquestador.** Sincroniza productos, listas y precios cada 6 h (599 precios a las 18:03 UTC); `push_orders_enabled = false`. No se apaga: cortar la integración de un tenant activo arriesga sus datos. Lo cubren el chequeo diario y las incidencias |

La spec 183 lo daba afuera por "servidor Sistel no responde (puerto 3448 cerrado desde afuera)". Ese motivo ya no vale. Por qué volvió Sistel no está explicado; conviene preguntarle a rawson.

## Trabajo adicional de P2

Lo resuelto fuera del plan original, una línea por issue (todas Done salvo indicación):

* **DEV-164** — #422: el contacto hijo de Odoo se colapsa en su empresa padre; dejó de abrir 18 de las 32 C7 de dimer. Cola de onboarding: 828 filas de hijos pasaron a `resuelto` (2752 → 1924 pendientes).
* **DEV-170** — #425: `parent_odoo_id` en el espejo (1738 partners con padre), también para cadenas empresa ← contacto ← contacto. Sin C7 nuevas ni vínculos inesperados. Otras 554 filas de la cola resueltas (1930 → 1376).
* **DEV-176** — #429: los pedidos de contactos hijos van al cliente del padre; `reconcile_orders_raw_customers("dimer")` asignó 199 pedidos. Quedan 12 sueltos (padres sin cliente) y 18 hijos fuera del espejo con SQL **sin correr**.
* **DEV-165** — #423: el espejo marca inactivas las listas que el ERP ya no devuelve. dimer: 45 activas, 2 inactivas.
* **DEV-167** — #424 y backoffice #318: el alta de clientes no asigna listas inactivas (abre L2 `lista_erp_inactiva`) y el backoffice muestra "En ERP: Activa" en el Paso 1. El caso "Inactiva" solo está cubierto por tests y datos; almaro no tiene listas inactivas.
* **DEV-171** — RLS: relevamiento (los schemas de tenant y `core` no son alcanzables con la anon key) y migración 205, aplicada en prod con OK de Faka (#426): `anon` y `authenticated` ya no ejecutan `get_del_corro_clients()`, `handle_new_user()` ni `rls_auto_enable()`.
* **DEV-174** — P8 (≈1650 abiertas): #428 las cierra cuando el producto sale del catálogo o del ERP. Las ~1640 restantes son reales (productos sin imagen), tema de catálogo. Hoy siguen abiertas: almaro 610, rawson 516, gonzales 399, el_gigante 68, dimer 60, benfresh 13; las 2 de rawson se cierran en el próximo sync de productos.
* **DEV-179** — #431: P4, P6 y C6 se cierran solas cuando el caso desaparece. Medición previa: hoy no cierra ninguna (los casos siguen vigentes en el ERP).
* **DEV-175** (Backlog) — revisión de P6, C6 y P4: 16 incidencias pasaron a `ignorada` (14 C6 y 2 P4 de benfresh). Siguen abiertas, esperando a la distribuidora: 19 P6 de gonzales, 4 C6 de clientes que siguen comprando y todo cordoba_frost.
* **DEV-166** — 526 clientes de dimer "vinculados a partners fuera del espejo": era un artefacto de la consulta. 525 sí están en el espejo (partner sin teléfono en Odoo) y el 2798 (partner 66205, `customer_rank = 0`) queda vinculado. Sin PR.
* **DEV-172** — #427: el conector Odoo usa `mobile` si no hay `phone` (con reintento sin el campo en Odoo 19). 214 partners de dimer toman el celular; 17 clientes pasaron del teléfono sintético al real, con el anterior en `datos_personales.dev172_telefono_anterior` y WhatsApp a revalidar. La issue figura Done; el comentario de #427 decía que quedaba abierta hasta el backfill, que se hizo.
* **DEV-168** — dimer, pedido 37012 de Panimas SpA: #432 compara el RUT chileno completo `cuerpo-DV`. El cliente 7204 se vinculó a mano al partner 65178 y el pedido salió solo (O5): `enviado_erp`, `S149590`. Queda el 7198 duplicado de 2099 y el `_normalize_cuit` del agente que borra la K (DEV-180).
* **DEV-173** — el_gigante, 30 C7: eran 15 pares de clientes con el mismo código. Se vincularon los 15 viejos a Galileo y las 30 C7 quedaron `resuelta`; hoy no queda ninguna abierta.
* **DEV-178** (En curso) — el_gigante, clientes con teléfono de relleno: eran 16, no 232. Se unieron 34 pares de duplicados (IA apagada en los contactos con relleno). Pendientes: grupo E (1987 y 2000, esperan el código correcto) y BENITEZ ROSA (101).
* **DEV-177** — #430 y backoffice #319: el alta masiva ya no duplica clientes por código (devuelve la fila en `ya_existe`). Probado solo con tests y smoke; no se probó la pantalla de importación para no crear clientes reales en almaro.

Abiertas sin trabajo hecho (Backlog): **DEV-180** (el agente guarda el RUT chileno sin dígito verificador), **DEV-181** (buscar el cliente en el espejo apenas un pedido cae en `pendiente_vinculo`, sin esperar al sync) y **DEV-182** (casos dudosos de la cola de onboarding de dimer y 18 hijos fuera del espejo).

## Pendiente de terceros

* **dimer, alta de clientes en Odoo (DEV-161, punto 3.4):** 7157 y 7166 no existen en Odoo; el alta con celular cargado destraba los pedidos 32468, 36413 y 32588 (O5). Hoy siguen en `pendiente_vinculo`.
* **dimer, 7 C7 abiertas (DEV-160, punto 3.3):** preguntas sin responder: Comercial Lazcano (376), Comercializadora El Siete (636), Beach An Foods (1346), Guzmán Maldonado / CyV (1533), y razón social de facturación de Aroas (360), Los Patricios (446) y Sonata (676). También la unión probable de 39816/13075 y 52681/14486 (duplicados) y qué hacer con la cola.
* **el_gigante, cliente 1682 (DEV-161):** vinculado al partner 260195 con otro nombre; Faka le pregunta si es el mismo comercio. Si no, se desvincula. También: código correcto de ERIKSON ROBERTO MARTIN (1987) y LESCANO LEONEL (2000), y si BENITEZ ROSA (101) sigue siendo cliente.
* **gonzales (DEV-150, punto 3.2):** preguntarle si de abril a septiembre de 2026 cargó pedidos por fuera de GEV. Decisión de Faka: cerrar octubre 2025 sin rellenar (recomendado) o reintentar el job entre 14 y 16 UTC (~2.000 pedidos, ~10 min).
* **gonzales, Xionico (DEV-175):** 19 combos P6 con SKU que el ERP no entrega (11 Formis, 7 de cereales y bolsitas, 1 Mogul Sandía); dar de baja los combos o cargar los SKU con precio. Y confirmar si se dieron de baja a propósito 4 clientes que siguen comprando: 1477 (gonzales) y 270081, 870002 y 260114 (el_gigante).
* **cordoba_frost (punto 5):** credenciales válidas de Cianbox. Sin eso sigue en pausa y la O12 queda abierta.
* **rawson:** explicar por qué volvió Sistel (el motivo de la spec 183 ya no vale).
* **benfresh:** limpiar los SKU duplicados 10003 y 89090074 de su ERP (las P4 se ignoraron).
* **Datos de dimer:** 18 clientes tienen teléfono real en Suplai que Odoo no tiene; dimer puede cargarlos.

## Pendiente de nuestro lado antes de cerrar P2

1. Puntos 1.1–1.3: correr DEV-156 (ventana en gonzales con partner de prueba) y DEV-157 (teléfonos y tokens de prueba).
2. Punto 2.1: esperar las corridas programadas del 03/11 al 09/11 y revisar las señales marcadas en DEV-158 (`incidencias.crece` con P8, `pendiente_vinculo` medido desde `last_error.at`, del_corro sin conteos).
3. Mirar en las próximas corridas: la `habituales_refresco` de dimer murió por `TimeoutError` el 02/11 07:50 UTC (1 job `dead` en 24 h, único hoy).
4. Spec: decidir si se reescriben o quedan como historial §2 "Estado actual" y §8 Fases (sin tocar).
5. Publicar el reporte final, comentar el link en DEV-163 y escribir el status update y el cierre del proyecto.
