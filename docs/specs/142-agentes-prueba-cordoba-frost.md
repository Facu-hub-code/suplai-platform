# 142 — Equipo de agentes: prueba en Córdoba Frost

**Estado:** Borrador. Se completa la línea base antes de la prueba 1.
**Fecha:** 2026-10-27
**Repos:** `suplai-platform` (este spec, resultados en `implementacion/cordoba_frost/outputs/`).
**Tenant:** `cordoba_frost` (ERP Cianbox, ver [120](./120-mcp-erp-cianbox.md)).
**Humano:** Faka, owner supervisor del tenant en noviembre de 2026.
**Relaciona:** [134](./134-mvp-equipo-de-agentes.md) y todos los specs 135–141.

---

## Objetivo

Comprobar en un tenant real y chico que el canal funciona de punta a punta (encargo, runs, traza, pregunta, contexto, reporte, correo) y medir los cinco criterios de éxito contra una línea base. La prueba 1 prioriza el cableado sobre la velocidad.

---

## Antes de empezar

| # | Paso | Cómo se verifica |
|---|------|------------------|
| 0.1 | Migraciones del 136 aplicadas en producción | `list_tables` del MCP de Supabase muestra `core.agentes_*` |
| 0.2 | Alta del tenant con `scripts/agentes_alta_tenant.py --schema cordoba_frost` | Tres bots `activo` en `/agentes/equipo`, certificado v1 cada uno |
| 0.3 | Proyecto `suplai-agentes` creado con Terraform y cuota de Claude en Vertex aprobada | `terraform plan` sin cambios pendientes |
| 0.4 | Run de humo del 138: el job ejecutado a mano llama solo `registrar_traza` y termina | El run pasa a `terminado` por el aviso de fin, no por el job de vencidos |
| 0.5 | Datos: pedidos e ítems de Córdoba Frost de los últimos 12 meses en `cordoba_frost.pedidos` / `items_pedido` | Consulta de solo lectura: cantidad de pedidos por mes, sin meses vacíos inesperados |
| 0.6 | Línea base medida (ver abajo) | Tabla de línea base completa en este spec |

### Línea base

Se mide una vez, a mano, el análisis equivalente sin el equipo de agentes: Faka le pide a Claude con el MCP actual «ventas del último año: tendencias, clientes que crecen y caen, productos y zonas».

| Medida | Valor |
|--------|-------|
| Mensajes del humano hasta tener el análisis | _a medir_ |
| Llamadas a tools del MCP | _a medir_ |
| Minutos de reloj | _a medir_ |
| Horas de implementador o customer success | _a medir_ |

---

## Prueba 1: análisis de ventas a pedido

### Pasos

1. Faka, en Claude con el conector de Córdoba Frost, escribe: «Haceme un análisis de las ventas del último año: tendencias, clientes que crecen y caen, productos y zonas.»
2. Claude llama `encargar_analisis` y responde con el link al trabajo.
3. Faka no escribe nada más salvo que un bot pregunte.
4. Durante el trabajo, Faka abre la pantalla Trabajos al menos una vez desde el link y una vez pregunta en Claude «¿cómo va?» (`ver_trabajos`).
5. Si el analista abre una pregunta, Faka la responde una vez desde Claude y, si hay otra, desde la Bandeja.
6. Llega el correo. Faka abre el reporte y el PDF.

### Datos esperados

| Momento | Qué tiene que pasar |
|---------|---------------------|
| Encargo | Un `core.agentes_trabajos` en `creado` y un evento `trabajo.creado` |
| Plan | Traza `plan` del jefe de cuenta con al menos 3 pasos, en menos de 10 min |
| Delegación | `trabajo.delegado` y un run del analista de ventas |
| Exportación | Uno o más `exportar_lote` con archivos en `agentes/cordoba_frost/{trabajo_id}/datos/` |
| Hallazgos | Al menos 5 eventos `hallazgo` con `datos_path` |
| Pregunta | Si existe, el trabajo pasa por `esperando_humano` solo si era bloqueante |
| Reporte | `core.agentes_reportes` con `web_path` y `pdf_path`; trabajo `terminado` |
| Correo | Un `core.agentes_avisos` con `enviado_at` y un `notification_delivery` entregado |
| Traza | Ningún run sin al menos un evento de traza; ningún evento sin `linea` |

### Verificación de los números

El reporte se valida contra una consulta propia de solo lectura sobre `cordoba_frost.pedidos`: total vendido del año, por mes y top 10 clientes. Diferencia aceptada: 0 % en totales (mismo filtro de estado `confirmado`), y el mismo top 10 en otro orden solo si hay empate.

---

## Prueba 2: análisis proactivo de conversaciones

### Pasos

1. Se habilita la agenda semanal del tenant.
2. El lunes a las 07:30 el scheduler emite `agenda.semanal`; el jefe de cuenta crea el trabajo (`origen=agenda`) y delega en el analista de conversaciones.
3. Faka no encarga nada. Recibe el correo cuando el reporte está listo.
4. Faka revisa en la Bandeja los motivos marcados «a confirmar» y acepta o corrige.
5. Se repite una segunda semana para ver si el contexto de la primera cambia el reporte.

### Datos esperados

| Momento | Qué tiene que pasar |
|---------|---------------------|
| Agenda | Un solo `agenda.semanal` por semana (clave idempotente) |
| Lote | `conversacion.cerrada` agrupado; ningún run por conversación individual |
| Clasificación | Cada conversación cerrada sin pedido de la semana con un motivo o «sin clasificar» |
| Propuesta | Los motivos generales como Propuesta L3 en la Bandeja |
| Semana 2 | El reporte cita el contexto aceptado en la semana 1 en su anexo |

### Verificación

Faka etiqueta a mano 20 conversaciones de la semana. El analista tiene que coincidir en al menos 15 (mismo umbral que la eval del 140).

---

## Pruebas de robustez

| Caso | Cómo se provoca | Resultado esperado |
|------|-----------------|--------------------|
| Runtime caído | Fake runtime que devuelve 500 durante 30 min, en el tenant `demo` (no en Córdoba Frost) | Eventos `pendiente` con backoff; el agente de WhatsApp responde normal; al volver, el trabajo sigue |
| Webhook repetido | Reenviar el mismo cuerpo firmado | Un solo cambio de estado |
| Run sin reporte | Prompt de prueba que termina sin `publicar_reporte` | Traza `error`, un relanzamiento, y `fallido` si se repite |
| Bot pausado | Pausar el analista desde Equipo durante un trabajo | El run vivo se cancela; el evento siguiente queda `descartado` y se ve en la traza |
| Token de un run cerrado | Reusar el token de un run ya terminado | `token_revocado` |
| Salida a internet | `curl https://example.com` desde el contenedor | Falla por la red |
| Bucket sin URL firmada | Listar el bucket con la cuenta del job | Falla por permisos |
| Certificado | Bajar `leer_datos` del analista a L1 | `exportar_lote` deja de estar en su `list_tools` en el siguiente run |

---

## Criterios de éxito

Las metas numéricas quedan abiertas hasta tener la línea base.

| Criterio | Cómo se mide | Fuente |
|----------|--------------|--------|
| El encargo sale con un solo pedido en Claude | Mensajes del humano por análisis, sin contar respuestas a preguntas de los bots | Conversación de Claude; `origen=claude` en el trabajo |
| El reporte llega sin intervención de Suplai | Horas de implementador y customer success por análisis | Registro manual de horas de la semana |
| El humano entiende el avance sin preguntar | Llamadas a `ver_trabajos` frente a aperturas de la traza | `mcp_auditoria` y Mixpanel `agentes_trabajo_abierto` |
| El contexto mejora el resultado | Preguntas respondidas y si el humano considera útil el reporte | `core.agentes_preguntas`; pregunta de 1 a 5 al pie del reporte |
| El cliente lo vuelve a pedir | Encargos repetidos por tenant en el mes | `core.agentes_trabajos` con `origen=claude` |

Los resultados de cada corrida se guardan en `implementacion/cordoba_frost/outputs/agentes-prueba-{n}-{fecha}.md`, con el link al trabajo, los números verificados y lo que falló.

## Después de las dos pruebas

Revisión con el cliente (etapa 5 del índice) antes de abrir la prueba 3. Entra a la revisión: el reporte de cada prueba, la tabla de criterios con la línea base y la lista de fallas de cableado encontradas.
