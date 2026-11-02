# P2 · Check final (DEV-163) — borrador del 2026-11-02

**Estado:** borrador. Adelanta lo verificable hoy en **solo lectura** (SQL contra Supabase `cvlbietibaaehgeimxgw` y requests sin credenciales). No se escribió nada en producción. Lo pendiente se corre cuando cierren las issues que lo bloquean.

Leyenda: ✅ verificado · ❌ no cumple · ⏳ pendiente (la issue entre paréntesis lo cierra)

## Resumen por punto

| # | Punto | Estado | Evidencia / lo que falta | Lo cierra |
|---|---|---|---|---|
| 1.1 | 3 fallas simuladas en gonzales (ERP caído, credenciales inválidas, respuesta vacía) | ⏳ | Runbook en `backend-supabase/docs/runbooks/dev-156-fallas-simuladas-gonzales.md`; hay que correrlo en prod | DEV-156 |
| 1.2 | Reenvío DEV-82 y O5 en gonzales | ⏳ | Prueba en prod, no leída hoy | DEV-156 / DEV-157 |
| 1.3 | Altas en almaro y DEV-83 con tokens reales | ⏳ | Prueba con tokens reales | DEV-157 |
| 2.1 | Chequeo diario: 7 corridas sin falsos positivos | ⏳ | Necesita una semana de corridas | DEV-158 |
| 2.2 | Alerta externa si el worker se cae | ⏳ | Prueba apagando el worker en ventana controlada. #417 y #420 mergeados (aviso por mail) | DEV-143 |
| 3.1 | Espejo de precios sin filas viejas | ✅ | Ver evidencia 3.1 | DEV-159 (Done) |
| 3.2 | gonzales: octubre 2025 resuelto o descartado; mayo–agosto 2026 confirmados | ⏳ | Diagnóstico en comentario de DEV-150: oct 2025 murió por timeout (GEV tarda 49,5 s en 01–03/10, límite 30 s), #419 mergeado. May–ago 2026: GEV responde 404 "No se encontraron registros", no es bug. Falta decisión de Faka (cerrar oct 2025 sin rellenar, recomendado, o reintentar el job entre 14 y 16 UTC) y preguntar a gonzales si abril–septiembre 2026 se cargó fuera de GEV | DEV-150 (Done en Linear, decisión abierta) |
| 3.3 | Las C7 de dimer tienen todas una decisión | ⏳ | Comentarios de DEV-160: 23 vinculadas, 2 `ignorada` (167, 296). Quedan **7 abiertas**: 3 de confianza media (360, 446, 676) y 4 preguntas a dimer (376, 636, 1346, 1533). Issue en Backlog | DEV-160 |
| 3.4 | el_gigante 1682 confirmado/desvinculado; dimer 7157 y 7166 con sus pedidos en Odoo | ⏳ | Depende de terceros (el_gigante, dimer). Issue en Todo, sin comentarios. Pedidos en `pendiente_vinculo`: 32468, 36413, 32588 | DEV-161 |
| 4.1 | Webhook de Slack rotado y logs sin credenciales | ⏳ | No se verificó hoy (rotación y revisión de logs de Railway) | DEV-151 |
| 4.2 | Request sin credenciales a `/{schema}/erp/*` responde 401 | ✅ | Ver evidencia 4.2 (falta la prueba del backoffice con sesión real, ver nota) | DEV-162 (Done) |
| 5 | cordoba_frost y rawson siguen afuera, con el motivo | ❌ parcial | cordoba_frost ✅ afuera. **rawson ❌: ya no está caído**, sincroniza precios hoy. Ver evidencia 5 | decisión de Faka |
| 6 | Spec "Reglas de integración ERP" actualizada; status update y cierre del proyecto | ⏳ | Secciones a tocar abajo. No se editó la spec | DEV-163 |

## Evidencia

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
| dimer | 5.039 | 5.039 | sí | 0 | 02/11 18:00 |
| el_gigante | 2.233 | 2.233 | sí | 0 | 02/11 18:02 |
| gonzales | 42.792 | 42.792 | sí | 0 | 02/11 18:03 |
| rawson | 599 | 599 | sí | 0 | 02/11 18:03 |

Los 6 tenants con conteo coinciden exacto y todas sus filas son de la última corrida. La corrida de las 18:00 UTC es posterior al deploy de #416 (comentario de DEV-159, 15:41 UTC), así que la poda ya corrió: la vista previa de DEV-159 anticipaba 400 filas a podar en dimer, y hoy no queda ninguna vieja.

Notas:
* `abmauri` tiene la tabla vacía (0 filas) y no tiene conteo.
* `cordoba_frost` (11.550 filas, última `synced_at` 07/10) y `del_corro` (6.280, filas desde el 19/09 hasta el 31/10) **no tienen fila en `erp_sync_conteos`**. No cuentan en este punto: cordoba_frost está fuera (punto 5) y del_corro carga por archivo (`SIN_API`).
* Pendiente de DEV-159 según su comentario: `erp_price_lists_raw` (cambia lo que significa `activa`, ahora cubierto por #423) y el ingest de GESCOM. La comparación de dimer contra Suplai "sin filas viejas" sigue sin correr aparte; este check solo prueba que el espejo no tiene sobrantes.
* La verificación es por `synced_at` de la corrida, no cruza contra lo que Odoo devuelve en vivo.

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

Corrido el 02/11 ~20:50 UTC. Coincide con lo que anotó DEV-162 (`/dimer/erp/config`, `/dimer/erp/dependency-health`, `/gonzales/erp/prices-diff` en 401; `bridge-config` protegido por `X-ERP-Ingest-Token`).

Falta, según el comentario de DEV-162: abrir la sección ERP del backoffice con una sesión real y confirmar que carga (la issue quedó Done sin ese chequeo). El resto de los endpoints de `/{schema}/erp/*` no se probó uno por uno: solo estos dos.

### 5 Límite: cordoba_frost y rawson

```sql
select d.schema_name, c.connector, c.last_sync_at, c.push_orders_enabled, c.orders_last_sync_at
from core.erp_connector_configs c join public.distribuidoras d on d.id = c.tenant_id
where d.schema_name in ('cordoba_frost','rawson');
```

| Tenant | Conector | `last_sync_at` | `orders_last_sync_at` | Motivo de estar afuera |
|---|---|---|---|---|
| cordoba_frost | Cianbox | 06/10 18:02 | 07/10 12:04 | ✅ Sigue afuera. Credenciales cambiadas: `Cianbox auth rejected: Usuario o contraseña inválidos` (spec 183). Mails silenciados con `SALUD_ERP_TENANTS_SIN_MAIL=cordoba_frost` (DEV-154) |
| rawson | Sistel | **02/11 13:28** | 20/10 18:07 | ❌ La spec 183 lo daba afuera por "servidor Sistel no responde (puerto 3448 cerrado desde afuera)" desde el 22/10. Hoy tiene `last_sync_at` del 02/11 y 599 precios sincronizados a las 18:03 UTC |

Ambos tenants están `activa = true` en `public.distribuidoras`.

Conclusión: la premisa del punto 5 vale para cordoba_frost y **no para rawson**. Hay que decidir: o rawson vuelve al alcance (y entra en los puntos 2 y 3), o se deja afuera por otro motivo (p. ej. sin pedidos, `push_orders_enabled = false`). Por qué volvió Sistel no está explicado; conviene preguntarle a rawson antes de anotar el motivo en el reporte final.

### Estado de DEV-150, DEV-160 y DEV-161 (según sus comentarios)

| Issue | Estado en Linear | Qué dice | Punto |
|---|---|---|---|
| DEV-150 | Done | #419 mergeado y desplegado en el worker (`3f5f045`). Oct 2025: timeout de GEV, ahora backfill por tramos. May–ago 2026: GEV no tiene registros. Quedan 2 decisiones de Faka (arriba) | 3.2 ⏳ |
| DEV-160 | Backlog | 7 C7 abiertas de 32 (3 media confianza, 4 preguntas a dimer). Falta correr el SQL que cierra las filas de contactos hijos en `erp_customer_onboarding_queue` | 3.3 ⏳ |
| DEV-161 | Todo | Sin comentarios. Depende de el_gigante (1682) y dimer (7157, 7166) | 3.4 ⏳ |

## Spec "Reglas de integración ERP": qué actualizar

**Dónde está:** no está en ninguno de los repos. `grep` en `backend-supabase/docs` y `suplai-platform/docs` no encuentra el título (las coincidencias de "Reglas de integración" son el runbook dev-156 y la spec 139 y la mencionan, no la contienen). Es un **documento de Linear** del proyecto P1: <https://linear.app/suplai-sales/document/reglas-de-integracion-erp-b72625bb22e3> (última edición 02/11 14:35 UTC). No se editó.

La §10 "Cambios de la implementación (02/11)" ya cubre DEV-82, DEV-83, DEV-107/154, DEV-142/152 y DEV-151. Falta lo mergeado después:

| PR | Qué cambió | Secciones a actualizar |
|---|---|---|
| backend-suplai#416 (DEV-159) | `load_prices_to_raw` poda de `erp_prices_raw` las filas (lista, SKU) que el ERP dejó de devolver, con corte por anomalía (30 %) | **Principio 4** ("nunca se borra por ausencia"): hoy contradice la poda; aclarar que el espejo crudo se poda y lo que se marca inactivo es lo de Suplai. **Principio 5** y §4.6 (corte por anomalía en precios). **§4.2** (nuevo caso: precio que el ERP ya no devuelve). **§10** (viñeta del sync de 6 h) |
| #417 y #420 (DEV-143) | Aviso si el worker se cae o deja de consumir la cola; #420 lo pasó de Slack a mail (aviso de caído y recuperado) | **§6 caso I3** y **§10 Monitoreo**: nuevo vigía del worker, canal de mail. Principio 8 (estado visible). Mencionar que la validación (apagar el worker) sigue pendiente |
| #418 (DEV-162) | `/{schema}/erp/*` exige sesión del back office (401 sin credenciales); `bridge-config` e ingest siguen con `X-ERP-Ingest-Token`; proxies de backoffice reenvían la sesión (product-management-app#317) | **§3** (arquitectura: quién llama a qué), **§7** (contrato: autenticación de endpoints) y **§10** |
| #419 (DEV-150) | Backfill de pedidos por tramos (3 días en GEV, 7 en el resto), partición hasta 1 día y 3 reintentos por día, timeout de 60 s durante el backfill | **O7** ("ventanas mensuales"): ahora mensual con tramos internos. **§3 Reintentos**. **§10** |
| #422 (DEV-164) | El contacto hijo de Odoo se colapsa en su empresa padre | **C7** (match ambiguo: no abre incidencia si es padre/hijo), **C2** (unir como contacto) y **C5**. Cierra el bug descripto en el comentario de DEV-160 |
| #423 (DEV-165) | El espejo de listas marca inactivas las que el ERP ya no devuelve | **L5** (hoy dice "la lista se marca inactiva": confirmar que ahora lo hace el espejo `erp_price_lists_raw`) y **Principio 4**. Cambia el significado de `activa` |
| #424 (DEV-167) | El alta de clientes no asigna listas inactivas en el ERP | **L1/L2/L3** (qué lista se asigna en el alta) y **§4.0**/C1 |

Además, §2 "Estado actual (2026-10-29)" está desactualizado (describe un mundo sin Redis ni worker) y **§8 Fases** no marca nada como hecho. Decidir si se reescribe o se deja como historial.

## Pendientes para armar el reporte final

1. Correr los puntos ⏳ cuando cierren DEV-156, 157, 158, 143, 151, 160 y 161.
2. Decidir DEV-150 (oct 2025) y rawson (punto 5).
3. Confirmar el backoffice con sesión real (DEV-162).
4. Publicar el reporte, comentar el link en DEV-163 y escribir el status update del proyecto.
