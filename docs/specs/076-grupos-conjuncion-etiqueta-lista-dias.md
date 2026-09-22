# 076 — Grupos por conjunción de etiqueta, lista y días

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/grupos-conjuncion`  
**Relaciona:** membresía usada por agendas (`agenda_sender._get_clientes_del_grupo`), estrategias (`_GROUP_CLIENTS_SQL` en `estrategias_service.py` y `estrategias_cycle_service.py`) y el conteo/preview de `routers/grupos.py` vía `sql_grupo_client_match_case`.

---

## Contexto

Crear grupo ofrece tres modos excluyentes: Por lista y días, Por etiqueta, Especiales. El API rechaza la mezcla con `GRUPO_MODES_CONFLICT`: “no combinados”.

Eso impide un grupo del estilo “etiqueta Mayorista **y** lista Norte **y** visita el lunes”. Hoy hay que aproximarlo con un solo eje y el resto se pierde.

La exclusión no está solo en el formulario. Hay tres resoluciones distintas:

| Lugar | Comportamiento actual |
|-------|------------------------|
| `routers/grupos.py` `_validate_grupo_modes` | Exactamente un modo. Lista y días tienen que ir juntos. |
| `services/grupos_membership.py` | `CASE`: si hay etiquetas, no evalúa lista ni días. |
| `agenda_sender._get_clientes_del_grupo` | Si hay `etiqueta_ids`, retorna por etiqueta y no mira lista ni días. |
| `_GROUP_CLIENTS_SQL` (estrategias, dos copias) | `OR` entre etiqueta, geo-zona y lista. Un cliente entra si cumple **cualquiera**. |

Un grupo guardado con los tres campos hoy o no se puede crear, o —si se persistiera— cada canal lo interpretaría distinto. Esta spec unifica el predicado.

Dentro de etiquetas, el match sigue siendo “cualquiera de las elegidas, incluidas hijas”. La conjunción nueva es **entre ejes**, no entre etiquetas.

---

## Objetivo

Poder definir un grupo manual con cualquier subconjunto no vacío de:

- etiquetas (opcional),
- lista de precios (opcional; null = no filtrar por lista),
- días de visita (opcional).

Un cliente entra solo si cumple **todos** los ejes que el grupo tenga cargados. Especiales y geo-zona siguen siendo modos aparte, no combinables con esos ejes.

### Métricas de éxito

- Preview, ficha del grupo, envío de agenda y audiencia de estrategia devuelven el mismo conjunto para el mismo grupo.
- Un grupo viejo de solo etiquetas, o de lista+días, conserva sus miembros.
- Lista en null no exige lista: alcanza con etiquetas, con días, o con ambos.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Semántica | AND de los ejes presentes. Eje ausente = no restringe. | Es la conjunción pedida. Null en lista significa “cualquiera”, no “clientes sin lista”. | Tratar lista null como `lista_precios_id IS NULL`: cambia el sentido de “sin elegir” y rompería grupos que ya guardan lista null con días. |
| Dentro de etiquetas | OR + descendientes, como hoy | “Estas etiquetas” ya se lee como unión. AND entre tags dejaría grupos vacíos en jerarquías. | Exigir todas las etiquetas a la vez. |
| Dentro de días | OR: el `dia_de_visita` del cliente está en el array | Igual que el modo lista actual. | AND de varios días sobre un solo `dia_de_visita`: imposible si el cliente tiene un día. |
| Mínimo para crear | Al menos un eje: etiquetas, lista o días | Si no, el grupo sería “todos los clientes”. | Seguir exigiendo lista **y** días juntos: impide “solo los del lunes” o “solo esta etiqueta y el lunes, cualquier lista”. |
| Especiales y geo-zona | Siguen excluidos del compuesto | Son otra definición (condición dinámica o zona). Mezclarlos con AND no estaba pedido y el `CASE` de especiales debe seguir ganando solo. | Un único formulario con los cinco ejes. |
| Vendedor | Sigue siendo AND opcional, solo junto al compuesto lista/etiqueta/días | Ya existe en el modo lista. No se ofrece en Especiales. | Aplicarlo también a geo-zona: fuera de este cambio. |
| Una sola función de match | Reescribir `sql_grupo_client_match_case` y hacer que agenda y las dos copias de `_GROUP_CLIENTS_SQL` la usen (o compartan el mismo fragmento) | Tres SQL divergentes es el riesgo real: el preview diría 12 y la agenda mandaría a 40. | Parchear solo el modal y el POST. |
| Grupos existentes | Sin backfill | Un grupo de un solo eje ya cumple el AND (los otros ejes están vacíos). | Migrar filas: no hay dato nuevo que inferir. |
| UI | Un solo formulario “Por etiqueta, lista y días” con los tres bloques visibles. Especiales queda como modo aparte. | Los tabs actuales esconden la combinación. | Dejar los dos tabs y un checkbox “combinar”: más estados y el mismo POST. |

Predicado del compuesto (todos los términos presentes se aplican):

```
activo_ai no es false
AND (vendedor_id del grupo IS NULL OR cliente en su cartera activa)
AND (etiqueta_ids vacío OR cliente tiene alguna etiqueta del set, con hijas)
AND (lista_precios_id IS NULL OR cliente.lista_precios_id = grupo.lista_precios_id)
AND (dias vacío OR lower(cliente.dia_de_visita) = ANY(dias))
```

Si el grupo es especial o de geo-zona, ese predicado no se evalúa: sigue el camino actual de ese modo.

`lista_precios_id` null **no** matchea “clientes sin lista asignada”. Para eso haría falta un literal explícito (fuera de v1).

---

## Alcance explícito

### Incluido (v1)

- POST/PATCH/preview de grupos aceptan etiqueta + lista opcional + días opcionales a la vez.
- Validación: compuesto válido con uno o más ejes; sigue 400 si se mezcla con `dynamic_condition` o `geo_zone_id`.
- Ya no hace falta mandar lista y días juntos.
- Preview, listado (conteo y muestra), detalle, `agenda_sender` y audiencia de estrategia usan el mismo AND.
- Modal: los bloques de etiquetas, lista (“Cualquiera” = null) y días se pueden completar juntos. Copy del encabezado alineado a esa conjunción.
- El filtro de vendedor sigue disponible en ese formulario.
- Tests de membresía que fijan el AND y la compatibilidad de grupos de un solo eje.

### Fuera de alcance

- AND entre varias etiquetas (sigue OR).
- Elegir explícitamente “clientes con lista null”.
- Combinar Especiales o geo-zona con etiquetas/lista/días.
- Varios días de visita por cliente (el cliente sigue teniendo un `dia_de_visita`).
- Reescribir grupos ya creados.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/grupos-conjuncion` | Validación, predicado único, preview, agenda, estrategias, tests |
| 2 | `product-management-app` | `feat/grupos-conjuncion` | Modal y preview con los tres ejes |

Backend primero: el modal nuevo manda un body que hoy responde 400.

---

## Migración de base de datos

Sin migración de BD. `grupos` ya tiene `lista_precios_id` (nullable en el modelo actual), `dias_visita` y `etiqueta_ids`.

- Seed / backfill: no.
- Rollback: volver el predicado al `CASE` / `OR` anterior. Los grupos nuevos que tengan dos ejes cargados pasarían a interpretarse por un solo eje (el que gane el `CASE`) o por el `OR` de estrategias. Por eso el rollback de código hay que hacerlo junto: no dejar el UI nuevo contra el predicado viejo.
- Riesgo: un grupo combinado mal resuelto en agenda manda de más. La unificación del SQL es parte del mismo PR de backend, no un follow-up.

---

## Contrato

`POST /{schema}/grupos` y el preview aceptan a la vez:

```json
{
  "nombre": "Norte mayorista lunes",
  "etiqueta_ids": [12],
  "lista_precios_id": null,
  "dias_visita": ["lunes"]
}
```

| Campos | Resultado |
|--------|-----------|
| Solo `etiqueta_ids` | Igual que hoy el modo etiqueta |
| `lista_precios_id` + `dias_visita`, sin etiquetas | Igual que hoy el modo lista |
| Etiquetas + lista y/o días | Intersección |
| Lista null + días | Solo esos días, cualquier lista |
| Etiquetas + lista null + sin días | Solo etiquetas |
| Ningún eje, sin especial ni zona | 400 `GRUPO_MODE_REQUIRED` |
| Cualquier eje manual + `dynamic_condition` o `geo_zone_id` | 400 `GRUPO_MODES_CONFLICT` |

PATCH deja de borrar `etiqueta_ids` cuando llega `lista_precios_id`, y al revés. Sigue limpiando los ejes manuales cuando el grupo pasa a especial o a geo-zona.

---

## Plan de prueba en CI/CD

- Actualizar `tests/test_grupos_membership.py`: el predicado compuesto exige AND; un grupo solo-etiqueta no referencia lista; lista null no agrega `cliente.lista_precios_id =`.
- Test del router: POST con etiqueta + días y lista null → 201; POST con etiqueta + `dynamic_condition` → 400; POST vacío → 400.
- Test de preview: fixture mínimo (o SQL del predicado afirmado) donde un cliente tiene la etiqueta y otro día, y no entra.
- Si estrategias y agenda dejan de duplicar el SQL, un test de caracterización alcanza con el fragmento compartido. Si se mantiene una copia, el test tiene que fallar cuando las copias divergen (mismo string de ejes AND).
- Checks del PR en verde. Sin smoke de migración.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`. Tenant con al menos dos clientes: uno con etiqueta A, lista L y visita lunes; otro con etiqueta A y visita martes; otro con visita lunes sin la etiqueta.

1. Crear grupo → un solo formulario de etiqueta, lista y días (Especiales aparte).
2. Elegir etiqueta A, lista en Cualquiera, día lunes. El preview muestra solo al primer cliente.
3. Guardar. Reabrir el grupo: los tres ejes siguen cargados (lista vacía no se pisó).
4. Crear otro grupo solo con etiqueta A. El preview incluye lunes y martes. No achicó respecto de hoy.
5. Crear grupo solo lista L + lunes, sin etiquetas. Mismos miembros que antes de este cambio.
6. Intentar Especiales junto con una etiqueta: la UI no lo ofrece; si se fuerza el JSON, el API responde 400.
7. Si hay una agenda o estrategia de prueba apuntando al grupo del paso 2, el destinatario resuelto es el mismo cliente del preview (no hace falta enviarla: mirar el conteo o el dry-run que ya use esa audiencia).

---

## Criterios de aceptación

### AC-1 Intersección

- **Given** cliente 1 (etiqueta A, lunes) y cliente 2 (etiqueta A, martes).
- **When** se crea el grupo con etiqueta A y día lunes, lista null.
- **Then** preview, detalle y resolución de agenda/estrategia incluyen solo al cliente 1.

### AC-2 Lista opcional

- **Given** dos clientes del lunes en listas distintas, ambos con etiqueta A.
- **When** el grupo es etiqueta A + lunes y lista null.
- **Then** entran los dos. Al setear la lista de uno, queda solo ese.

### AC-3 Grupos viejos

- **Given** un grupo existente solo con `etiqueta_ids`, y otro solo con lista+días.
- **When** se resuelve la membresía después del deploy.
- **Then** los conjuntos no cambian.

### AC-4 Especiales no se mezclan

- **Given** un body con `dynamic_condition=churn_risk` y `etiqueta_ids=[1]`.
- **When** POST.
- **Then** 400. No se persiste el grupo.
