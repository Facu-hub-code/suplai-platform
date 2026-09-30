# 089 — Validar el WhatsApp antes del primer envío

**Estado:** Borrador  
**Fecha:** 2026-09-30  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/validacion-whatsapp-previa`  
**Serie:** Prospección outbound v2 (087 a 092).  
**Relaciona:** [070](./070-whatsapp-estado-webhook-agenda.md) (estado `whatsapp_estado` por webhook), [083](./083-campana-outbound-mapas.md) (búsqueda, selección y cola), [087](./087-salud-numero-metricas-plantillas.md) (salud del número), [092](./092-directorio-compartido-suplai.md) (caché compartida).

---

## Objetivo

Hoy un teléfono del directorio recién se sabe si tiene WhatsApp cuando Meta rechaza el HSM con `131026` (spec 070). Ese rechazo ya gastó un intento, cuenta para el cupo y es una señal más en contra del número. Este spec valida el teléfono **antes** de que el operador lo pueda tildar, con un proveedor externo (checknumber.ai en v1), y cachea el resultado.

### Métricas de éxito

- En campañas outbound, la tasa de `131026` sobre envíos aceptados baja a menos del 2%.
- Ningún comercio sin WhatsApp confirmado entra a la cola de envío.
- El costo de validar queda visible en el costo de la campaña y no supera el 5% del costo de búsqueda.

---

## Investigación: checknumber.ai

Fuente: sitio y documentación pública, septiembre 2026. Hay que confirmarlo con una cuenta de prueba (el proveedor da 1.000 chequeos gratis).

| Tema | Hallazgo |
|------|----------|
| Qué hace | Chequeo pasivo: dice si el número tiene cuenta de WhatsApp. No manda mensajes ni notifica al dueño |
| Tipos de tarea | `ws` (registrado sí o no, US$ 0,90 cada 10.000), `ws_advanced` (tiempo real sin caché, US$ 1 cada 10.000), `ws_active` (más días de actividad y si es cuenta **Business**, US$ 1,80 cada 10.000), `ws_avatar` (edad y género estimados por la foto, US$ 3,80 cada 10.000) |
| API | Asíncrona. `POST https://api.checknumber.ai/v1/tasks` con un archivo de números E.164 (uno por línea) y `task_type`. Después `POST /v1/gettasks` con `task_id` hasta `status = exported`, y se baja `result_url`. Header `X-API-Key` |
| Cobro | Prepago, mínimo US$ 20, sin vencimiento. Se cobran solo los chequeos exitosos. Los 400 y 500 no se cobran |
| Latencia | No publicada. Es un batch: hay que medir cuánto tarda un lote de 300 números |
| Precisión | No publicada. Hay que medirla contra envíos reales (ver plan de prueba) |

**Costo real:** con `ws_active`, validar 1.000 comercios cuesta US$ 0,18. La búsqueda de esos 1.000 en Google Places cuesta alrededor de US$ 35. Validar es menos del 1% del costo de la campaña.

**Por qué `ws_active` y no `ws`:** por US$ 0,08 más cada 1.000 trae si la cuenta es **Business** y cuántos días lleva activa. Un comercio con WhatsApp Business es mejor candidato (es un número de trabajo, no el celular personal del dueño), y una cuenta inactiva hace meses no va a responder. No se usa `ws_avatar`: la edad y el género estimados por la foto son datos personales sensibles que no necesitamos.

### Riesgos

- **Términos de Meta.** checknumber.ai no es un proveedor oficial de Meta. Usa métodos no oficiales para consultar el registro. El chequeo no pasa por nuestro número ni por nuestro WABA, así que no afecta la calidad del número. El riesgo es de dependencia: el servicio puede dejar de funcionar si Meta lo bloquea. La Cloud API no tiene un endpoint oficial equivalente (el `/contacts` de la API On-Premises se discontinuó).
- **Política de mensajería de WhatsApp.** Validar que el número existe **no** reemplaza el opt-in que pide la política de WhatsApp Business para iniciar conversaciones. Es un riesgo que ya asumió 083 (primer mensaje a un comercio con teléfono público) y que se mitiga con el tope diario, la baja inmediata y los guards de 087. Este spec no lo resuelve y hay que dejarlo escrito.
- **Datos personales (Ley 25.326).** Mandamos teléfonos a un tercero fuera del país. Son teléfonos comerciales publicados, pero hay que revisar los términos de privacidad del proveedor, que no guarde las listas y que haya un acuerdo de tratamiento de datos.
- **Proveedor caído.** Si no responde, no se valida y no se envía. El webhook `131026` de 070 sigue como respaldo, no como reemplazo.
- **Segundo proveedor posible.** Outscraper (spec 090) tiene un enriquecimiento `whatsapp_checker` y un `phones_enricher_service` que dice si la línea es móvil o fija. Si 090 elige Outscraper, conviene comparar precio y precisión de su checker contra checknumber en la misma muestra, y quedarse con uno solo para no duplicar el costo.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Interfaz | `PhoneValidationProvider` con `validate_batch(phones) -> results`. v1 implementa `checknumber` | Mismo criterio que el directorio en 083: el precio y la disponibilidad de un proveedor no oficial pueden cambiar | Llamar a checknumber desde el servicio de campaña |
| Momento | Después de la búsqueda en el directorio y antes de que la lista se pueda tildar | El operador tiene que ver cuántos comercios son contactables de verdad antes de publicar. Validar recién al enviar esconde el número real | Validar al publicar; validar en el momento del envío de cada HSM |
| Tipo de tarea | `ws_active` | Trae si es Business y la actividad por muy poca diferencia de precio | `ws` pelado; `ws_avatar` |
| Sin resultado | Un teléfono sin resultado del proveedor no se puede tildar | La regla del usuario: no se envía sin corroborar el número | Dejarlo tildar con un aviso |
| Caché | Resultado guardado con fecha. Vigencia 90 días para `sí` y 30 días para `no` | Un número con WhatsApp suele seguir teniéndolo. Un `no` puede pasar a `sí` si el comercio instala WhatsApp Business | Validar siempre; guardar para siempre |
| Dónde se guarda | En el directorio compartido de 092 (`core.places`) cuando existe; mientras tanto, en `campaign_prospect` y en `clients` | El resultado depende del teléfono, no del tenant. Validar el mismo número para dos distribuidoras es pagar dos veces | Solo por tenant |
| Relación con 070 | La validación escribe `whatsapp_estado = existente` o `no_existente` con `whatsapp_existencia_verificada_at` y fuente `checknumber`. El webhook sigue pudiendo cambiarlo | Un solo estado de WhatsApp por cliente, el mismo que ya lee el resto del producto | Un estado paralelo solo para prospectos |
| Business vs personal | Se muestra en la lista y sirve de filtro. No bloquea | Hay kioscos que usan el WhatsApp personal. Bloquearlos deja afuera clientes reales | Validar solo cuentas Business |
| Costo | Columna `validation_cost` en `campaign_cost_daily` | El costo por cliente nuevo de 083 tiene que incluir todo lo que se gasta | Absorberlo sin mostrarlo |

---

## Alcance explícito

### Incluido (v1)

- Proveedor `checknumber` con `ws_active`, detrás de la interfaz.
- Paso de validación en la búsqueda del wizard de 083, con progreso («Validando WhatsApp de 312 comercios…»).
- Columna en la lista del wizard: WhatsApp (sí, no, sin validar) y Business (sí o no).
- Filtro «Solo WhatsApp Business».
- Caché con vigencia y lectura desde `core.places` si 092 ya existe.
- Costo de validación en la campaña.
- Revalidar antes de enviar si el resultado venció mientras el prospecto estaba en la cola.

### Fuera de alcance

- Validar la cartera de clientes existentes. Se puede hacer después con el mismo proveedor, pero no es parte de prospección.
- Validar teléfonos que un comercio pasa en el chat (el decisor de 084). Ese número ya vino de una persona, y el HSM del decisor es uno solo.
- Un segundo proveedor implementado. La interfaz queda lista.
- Datos de edad, género o foto.

---

## Flujo

```text
Buscar en directorio (083 / 090 / 092)
  → teléfonos normalizados E.164, sin duplicados, sin clientes actuales, sin opt-out
  → ¿hay resultado vigente en caché? sí → usarlo
  → no → lote al proveedor (tarea asíncrona)
  → polling con backoff hasta exported (tope 10 min)
  → guardar resultados
  → la lista del wizard habilita solo los que dieron WhatsApp = sí
```

Si el lote no termina en 10 minutos, los que no tienen resultado quedan «sin validar» y no se pueden tildar. El operador puede reintentar.

---

## Requisitos funcionales

- `RF-1` `POST /{schema}/campanas-outbound/{id}/validate-phones` arranca la validación del resultado de búsqueda y devuelve un `job_id`. `GET .../validate-phones/{job_id}` devuelve progreso y resultados.
- `RF-2` Antes de llamar al proveedor, se descartan los teléfonos con resultado vigente en caché.
- `RF-3` Un prospecto sin `whatsapp = sí` vigente no se puede tildar ni entrar a la cola.
- `RF-4` Al publicar, si un resultado venció, se revalida ese teléfono antes del HSM. Si da `no`, sale de la cola.
- `RF-5` El resultado actualiza `whatsapp_estado` y `whatsapp_existencia_verificada_at` del cliente prospecto, con fuente `checknumber`. Nunca pisa `validado` (regla de 070).
- `RF-6` El costo del lote se suma a `campaign_cost_daily.validation_cost` con el precio vigente del proveedor.
- `RF-7` Proveedor caído o sin saldo: error accionable en el wizard («No pudimos validar los números. No se va a enviar nada hasta validar.»). No se publica.

## Requisitos no funcionales

- `RNF-1` La API key vive en config de plataforma, no en el front ni en el tenant.
- `RNF-2` Un lote por búsqueda, no un request por teléfono.
- `RNF-3` Logs con `campaign_id`, cantidad y resultado agregado. Sin teléfonos.
- `RNF-4` El precio del proveedor sale de `core.directory_provider` (o una tabla hermana), editable sin deploy.

---

## Criterios de aceptación

### `AC-1` Sin WhatsApp no se tilda

- **Given** una búsqueda con 10 teléfonos y el proveedor dice que 3 no tienen WhatsApp.
- **When** el operador ve la lista.
- **Then** esos 3 aparecen con «Sin WhatsApp» y no se pueden tildar.

### `AC-2` Caché

- **Given** un teléfono validado hace 20 días con `sí`.
- **When** otra campaña lo encuentra.
- **Then** no se llama al proveedor para ese teléfono y el costo de validación no lo incluye.

### `AC-3` Proveedor caído

- **Given** el proveedor devuelve 500.
- **When** se valida.
- **Then** nadie se puede tildar, el wizard muestra el error y no se cobra nada.

### `AC-4` Revalidación en la cola

- **Given** un prospecto en cola cuyo resultado venció.
- **When** llega su turno de envío.
- **Then** se revalida y, si da `no`, no sale el HSM y queda «Sin WhatsApp».

### `AC-5` No pisa un validado

- **Given** un cliente con `whatsapp_estado = validado`.
- **When** el proveedor dice `no`.
- **Then** el estado no cambia y queda un evento para revisar.

---

## Casos borde

- `CB-1` Teléfono fijo sin WhatsApp: el proveedor dice `no`. Se muestra «Fijo o sin WhatsApp».
- `CB-2` Teléfono mal formado en el directorio: no se manda al proveedor, figura «Teléfono inválido».
- `CB-3` Lote a medio terminar: los que ya tienen resultado se guardan, el resto queda «sin validar».
- `CB-4` El proveedor dice `sí` y Meta después devuelve `131026`: gana Meta (070 lo marca `no_existente`) y se registra el desacuerdo para medir la precisión del proveedor.

---

## Migración de base de datos

- `{schema}.campaign_prospect`: `whatsapp_check` text (`yes` | `no` | `unknown`), `whatsapp_business` boolean null, `whatsapp_active_days` int null, `whatsapp_checked_at` timestamptz, `whatsapp_check_provider` text.
- `{schema}.campaign_cost_daily`: `validation_cost numeric NOT NULL DEFAULT 0`.
- `core.phone_validation_provider`: `id`, `price_per_check_usd`, `task_type`, `enabled`. Seed `checknumber`, US$ 0,00018, `ws_active`.
- `core.phone_validation_job`: `id`, `schema_name`, `campaign_id`, `provider_id`, `provider_task_id`, `status`, `total`, `done`, `created_at`, `finished_at`.
- `clients.whatsapp_validado_por` o la fuente de existencia: sumar el valor `checknumber` al enum o check si lo tiene.
- Cuando exista 092, el resultado se escribe también en `core.places`.

**Backfill:** ninguno. Los prospectos ya enviados tienen el resultado real de Meta.

**Rollback:** apagar el provider (`enabled = false`) vuelve al flujo de 083 **solo** con un flag explícito de plataforma; sin flag, sin proveedor no se publica.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-outbound-v2` | Este spec |
| 2 | `backend-supabase` | `feat/validacion-whatsapp-previa` | Migración, provider, job, caché, revalidación en la cola |
| 3 | `product-management-app` | `feat/validacion-whatsapp-previa` | Progreso, columnas y filtro en el wizard outbound |

No depende de 087, pero conviene mergear 087 antes: juntos son los dos resguardos del número.

---

## Plan de prueba en CI/CD

- **Backend:** provider fake (lote de 5, 2 `no`). Caché vigente evita la llamada. Vencido revalida. 500 del proveedor bloquea la publicación. `validado` no se pisa. Costo sumado con el precio de config.
- **Backoffice:** `tsc --noEmit`. Filas `no` y `unknown` no tildables.
- Gap: checknumber no se llama en CI.

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` con zona y cuenta de checknumber de prueba (1.000 chequeos gratis).

1. **Medir la precisión antes de integrar.** Tomar 200 teléfonos de prospectos ya enviados en campañas de 083 (se sabe cuáles dieron `131026` y cuáles `delivered`). Pasarlos por la plataforma web de checknumber. Anotar coincidencias. Si el acuerdo es menor al 95%, parar y revisar el proveedor.
2. Medir la latencia de un lote de 300.
3. En el wizard, buscar en una zona. Ver el progreso de validación y las columnas WhatsApp y Business.
4. Intentar tildar un «Sin WhatsApp»: no se puede.
5. Repetir la búsqueda: no se vuelve a cobrar la validación.
6. Poner una API key inválida: el wizard muestra el error y no deja publicar.
