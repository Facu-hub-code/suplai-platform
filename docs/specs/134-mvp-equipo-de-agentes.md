# 134 — MVP del equipo de agentes: índice

**Estado:** Borrador. Las decisiones de producto están cerradas (27/10/2026); las técnicas de cada spec quedan para revisar.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase`, `product-management-app` (backoffice agéntico), `suplai-platform` (estos specs).
**Relaciona:** [132](./132-mcp-para-agentes-y-humanos.md) (superficie MCP, gobierno, borradores, lotes, eventos y memoria), [125](./125-notificaciones-cola-canales.md) (cola de avisos), [120](./120-mcp-erp-cianbox.md) (ERP de Córdoba Frost), [073](./073-mixpanel-analytics.md) (métricas).
**Fuente:** documento de producto «MVP: equipo de agentes de Suplai Sales» (27/10/2026, Faka) y «Relación entre agentes y humanos en Suplai Sales».

---

## Objetivo

Un usuario de la distribuidora encarga desde Claude un análisis de ventas o de conversaciones. Un equipo de tres bots lo hace en segundo plano, deja traza de cada paso en el backoffice agéntico y avisa por correo cuando el reporte está listo. El humano puede preguntar cómo va y aportar contexto en cualquier momento.

El MVP prueba tres cosas:

1. Delegar un análisis grande le ahorra tiempo real al usuario.
2. La traza le permite entender el avance sin preguntar.
3. El contexto que aporta mejora el resultado.

**Fuera del MVP:** más de un rol humano, agrupación por corporación, catálogo como caso principal y autonomía L4 o L5 en acciones que tocan al cliente final. La prueba 3 (activación) es el siguiente paso, pero el modelo de datos y los permisos ya la contemplan.

---

## Specs

| # | Spec | Repo principal | Contenido |
|---|------|----------------|-----------|
| 135 | [Backoffice agéntico](./135-backoffice-agentico.md) | `product-management-app` | Cinco pantallas, rutas, permisos y componentes. Trabajos con la traza en carriles |
| 136 | [Modelo de datos](./136-agentes-modelo-de-datos.md) | `backend-supabase` | Diez entidades, migraciones y versionado de certificados |
| 137 | [Eventos, webhooks y scheduler](./137-agentes-eventos-webhooks-scheduler.md) | `backend-supabase` | Emisión, firma, idempotencia, reintentos y agendas |
| 138 | [Runtime en Google Cloud](./138-agentes-adaptador-runtime.md) | `backend-supabase`, `suplai-platform` | Cloud Run jobs + Claude Agent SDK en Vertex, una ejecución por bot, Terraform |
| 139 | [Tools nuevas en los dos MCP](./139-agentes-tools-mcp.md) | `backend-supabase` | Contratos, permisos por rol de bot y conversión en Propuesta |
| 140 | [Bots del MVP](./140-agentes-bots-mvp.md) | `backend-supabase` | Prompt, tools y certificado inicial de los tres bots |
| 141 | [Reportes](./141-agentes-reportes.md) | `backend-supabase` | Web y PDF, bucket, links firmados y correo |
| 142 | [Prueba en Córdoba Frost](./142-agentes-prueba-cordoba-frost.md) | `suplai-platform` | Pasos, datos esperados y verificación de cada criterio |

---

## Orden de construcción

```text
Etapa 1 — Ver
  136 modelo de datos (Trabajo, Run, EventoTraza, Bot, Certificado)
  135 pantalla Trabajos leyendo datos sembrados a mano
  139 encargar_analisis, ver_trabajos, registrar_traza

Etapa 2 — Cablear
  139 token por run en el MCP de agentes (primero: vale para cualquier runtime)
  138 Terraform del proyecto de agentes, imagen y adaptador gcp_cloud_run
  137 outbox, aviso de fin firmado, scheduler
  139 exportar_lote, crear_pregunta, leer_contexto, publicar_reporte

Etapa 3 — Trabajar solos
  140 jefe de cuenta + analista de ventas
  141 reporte web, PDF y correo
  142 prueba 1 en Córdoba Frost

Etapa 4 — Proactivo
  140 analista de conversaciones
  137 agenda semanal y conversacion.cerrada
  142 prueba 2

Etapa 5 — Revisión con el cliente
```

El backend se mergea antes que el backoffice en cada etapa. Una etapa no empieza sin la anterior en producción.

---

## Principios (valen para todos los specs)

1. La gobernanza la aplica el servidor, no el prompt. Cada token de run expone solo las tools del certificado de su bot. Una acción fuera de su autonomía se guarda como Propuesta: no se ejecuta ni falla.
2. Un solo backend con dos fachadas MCP. La lógica de dominio no se duplica.
3. Nada por polling. Todo despierta por evento o por agenda.
4. Todo Trabajo tiene un humano asignado y uno o más bots delegados.
5. Cada paso de un agente deja traza. Un paso sin traza es un error.
6. El runtime es reemplazable. Ningún spec depende de Cloud Run ni de Vertex fuera del adaptador.
7. Aislamiento por tenant. Un equipo de agentes solo ve los datos de su distribuidora.
8. Si el equipo de agentes falla, el agente de WhatsApp sigue vendiendo igual.
9. Los certificados y la configuración sensible se editan solo por formulario web en el backoffice. Claude consulta y manda el link, no edita.

---

## Decisiones de producto (cerradas el 27/10/2026)

| # | Tema | Decisión |
|---|------|----------|
| 1 | Runtime | Google Cloud: Cloud Run jobs + Claude Agent SDK con Claude en Vertex, una ejecución por bot (revisada el 27/10; antes era Grok en Cursor) |
| 2 | Alcance | Prueba de concepto para entender la infraestructura de agentes en GCP. El costo de GCP no es una restricción. Toda la infra de Suplai va a migrar a GCP más adelante |
| 3 | Cliente de las pruebas | Córdoba Frost (`cordoba_frost`, ERP Cianbox) |
| 4 | Usuario humano | Faka como owner supervisor de Córdoba Frost en noviembre. Un solo rol humano |
| 5 | Formato del reporte | Página web en el bucket y PDF |
| 6 | Tiempo de un análisis | Lo fija el spec 138. La prueba 1 prioriza el cableado sobre la velocidad |
| 7 | Cuándo escribe el activador | Dentro de la ventana de 24 horas de WhatsApp y por agendas de Suplai |

---

## Cómo encaja con el spec 132

El 132 ya dejó en `main` del backend buena parte de la base: borradores con riesgo e idempotencia (`core.mcp_borradores`), lotes que aprueba el dueño (`core.mcp_lotes`), cola de eventos (`core.mcp_eventos`), memoria del tenant (`core.tenant_memoria`), tokens OAuth por rol (`ROLES_AGENTE`) y kill switch (`editar_gobierno`). Este MVP construye encima y no lo duplica.

| Concepto del MVP | Qué reutiliza del 132 | Qué cambia |
|------------------|------------------------|------------|
| Propuesta | `core.mcp_borradores` en `pendiente_aprobacion` | Se suma `trabajo_id` y la decisión del humano. Se resuelve una por una en la Bandeja, además del lote por email |
| Certificado de autonomía | `metadata.gobierno.autonomia` como default del tenant | Tabla versionada por bot. El certificado manda sobre el default |
| Bot | `ROLES_AGENTE` | Nuevos roles `analista_ventas` y `analista_conversaciones`. Token por run firmado por el backend |
| Fachada de agentes | `mcp_server/` y `services/mcp_*` | Segundo endpoint `/agentes/mcp` con token por run. Mismas tools y servicios |
| Eventos | `core.mcp_eventos` (lectura con cursor) | Outbox `core.agentes_eventos` que se entrega por webhook. Ningún bot hace polling |
| Memoria | `ver_memoria`, `editar_memoria` | El Contexto marcado como «candidato a regla» se propone como edición del playbook |
| `editar_gobierno` | Pausar y reanudar | Cambiar autonomía y límites deja de estar en el MCP (principio 9): devuelve el link al formulario |

El último punto modifica el 132. Se anota allá cuando se implemente el 139.

---

## Glosario

| Término | Significado |
|---------|-------------|
| Trabajo | Un encargo del humano, con su humano asignado y sus bots delegados |
| Run | Una ejecución de un bot en el runtime |
| Traza | La secuencia de eventos de un Trabajo, visible en carriles |
| Pregunta | Lo que un bot no puede explicar sin el humano |
| Contexto | Información del mundo real que aporta el humano y la máquina no ve |
| Propuesta | Una acción que excede la autonomía del bot y espera la decisión del humano |
| Certificado de autonomía | Ficha versionada de un bot con su nivel por tarea |
| Backoffice agéntico | La sección nueva de control de agentes, distinta del backoffice operativo |
| Ventana de WhatsApp | 24 horas desde el último mensaje del comercio |
