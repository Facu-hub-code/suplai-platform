# 078 — Field: ruta sugerida desde el punto de partida

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `field-app`  
**Ramas sugeridas:** `feat/field-ruta-sugerida`  
**Relaciona:** home del vendedor (`VendedorAppService.get_home`, `FieldTaskService._fetch_route_pdvs_conn`), coordenadas en `{schema}.client_locations`. La lista de herramientas que abre el editor del punto de partida está en [079](./079-vendedores-herramientas-y-reporte.md). El audio del supervisor nombra estos PDV en [080](./080-supervisor-virtual-agendas.md).

---

## Contexto

La ruta del día ya existe: zonas del vendedor cuyo `dia_visita` es hoy. El home las devuelve con lat/lng de la location primaria y las ordena **por nombre** (`ORDER BY nombre ASC` en `_fetch_route_pdvs_conn`).

El vendedor no tiene un orden de calle. Preguntarle al ERP un ruteo óptimo (TSP) no aporta: una jornada es del orden de decenas de paradas, no cientos, y muchas locations no tienen coordenada. En `el_gigante` hay coordenada en 640 de 1694 locations.

Lo que falta es un punto de partida por vendedor (depósito, casa, primer barrio) y una sugerencia estable: primero la zona más cercana, después los comercios de esa zona en cadena corta.

---

## Objetivo

Si el supervisor carga un punto de partida, Field muestra la ruta del día agrupada por zona y, dentro de cada zona, en el orden de una recorrida sugerida. Sin punto de partida, la lista sigue alfabética.

### Métricas de éxito

- Con punto de partida y coordenadas, el primer PDV con coordenada de la primera zona es el más cercano al origen, no el primero del alfabeto.
- Un PDV sin coordenada aparece al final de su zona, no desaparece.
- Sin punto de partida, el orden del home es el actual (nombre).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Algoritmo | Vecino más cercano con distancia Haversine, por zona | Con 20–80 paradas el costo es despreciable y el resultado se explica (“el que sigue es el más cerca”). | TSP / OR-Tools: el óptimo no se nota en la calle y hay que operar otro servicio. Ordenar solo por latitud: cruza la ciudad en zigzag. |
| Orden de zonas | Goloso: desde la posición actual (el origen, luego el último PDV de la zona anterior), la zona restante cuyo centroide esté más cerca | Encadena la jornada. El centroide es la media de los PDV de esa zona que sí tienen coordenada. | Ordenar todas las zonas solo contra el origen: la segunda zona puede quedar del otro lado de la ciudad. Orden fijo de `geo_zones.id`: no tiene relación con la calle. |
| Zona sin centroide | Al final, por nombre de zona. Sus PDV, alfabéticos | Sin un punto no hay distancia que respetar. | Excluir la zona del día: el vendedor dejaría de ver cartera. |
| PDV sin coordenada | Al final de su zona, por nombre | Sigue en la lista. No se le inventa una posición. | Interpolar con la dirección: geocodificar en el request del home alarga el endpoint y gasta cuota de mapas. |
| Cuándo se calcula | Al armar el home, en memoria, sobre la lista que ya devuelve la query | La ruta cambia si cambia la zona del día o el pin. Un snapshot de anoche queda viejo. | Tabla `ruta_sugerida` materializada de madrugada: hay que invalidarla en cada cambio de pin, zona o location. |
| Sin pin | `orden = alfabetico`, mismo `ORDER BY nombre` de hoy | El tenant que no cargó el origen no ve un orden arbitrario distinto al que ya conoce. | Centro de la ciudad del tenant: una sugerencia que nadie pidió y que parece oficial. |
| Dónde vive el pin | Columnas en `{schema}.vendedores`: `partida_latitude`, `partida_longitude`, `partida_direccion` | Es un dato del vendedor, igual que el teléfono. Una sola fila, sin tabla nueva. | Pin en `metadata` JSON: no se indexa ni se valida el par lat/lng. Pin único de la distribuidora: dos vendedores no salen del mismo lugar. |
| Editor | Ficha del vendedor en el backoffice: dirección que se geocodifica con el servicio de direcciones ya existente, y lat/lng editables si el pin quedó mal. La tarjeta “Punto de partida” de la spec 079 abre ese mismo editor | No hace falta un mapa nuevo para la v1. El geocoder ya está. | Mapa embebido obligatorio en esta entrega: acopla la ficha al SDK de Maps y al puerto 3000 para un dato que es un par de números. |
| Field | Agrupa por zona en `zona_orden` y, dentro, por `orden_sugerido`. El vendedor puede ocultar un PDV como hoy | La sugerencia es una lista, no una ruta bloqueada. No hay orden de visita que el sistema exija cumplir. | Polilínea en mapa y navegación turno a turno: otro producto. |

Empate de distancia: gana el `pdv_id` menor, para que el orden no salte entre requests.

---

## Alcance explícito

### Incluido (v1)

- Columnas de punto de partida en `vendedores`.
- PATCH del vendedor acepta las tres columnas. Latitud fuera de \[-90, 90\] o longitud fuera de \[-180, 180\] responde 422.
- Home del vendedor: cada ítem trae `orden_sugerido` (1..n en el día) y `zona_orden`. El bloque `ruta` trae `orden: "sugerido" | "alfabetico"` y `partida: { latitude, longitude, direccion } | null`.
- Field agrupa la lista de “Mi Día” por zona, en ese orden. Dentro de la zona, el orden sugerido. La zona se ve como encabezado (nombre y color que ya vienen en el ítem).
- PDV sin coordenada al final de su zona.

### Fuera de alcance

- Ruta óptima (TSP), tráfico, horarios de apertura o una sola vuelta al origen.
- Geocodificar en el momento del home los PDV que no tienen coordenada.
- Obligar al vendedor a seguir el orden, ni marcarlo como visita hecha por GPS.
- Mapa de la recorrida en Field.
- Reordenar la cartera completa fuera del día de visita.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/field-ruta-sugerida` | Migración, orden en el home, PATCH del pin, tests del orden |
| 2 | `product-management-app` | `feat/field-ruta-sugerida` | Campos en la ficha del vendedor. Puede mergearse después del backend |
| 3 | `field-app` | `feat/field-ruta-sugerida` | Agrupar y ordenar con los campos nuevos. Sin el backend, ignora el orden y sigue el array como hoy |

Merge: backend primero. Field y backoffice no se bloquean entre sí.

---

## Migración de base de datos

En cada schema de tenant con tabla `vendedores`:

```sql
ALTER TABLE {schema}.vendedores
  ADD COLUMN IF NOT EXISTS partida_latitude double precision,
  ADD COLUMN IF NOT EXISTS partida_longitude double precision,
  ADD COLUMN IF NOT EXISTS partida_direccion text;
```

Sin backfill: NULL significa orden alfabético. Sin índice: el home lee una fila por vendedor.

Rollback: dejar de leer las columnas. Borrarlas es opcional y no hace falta para revertir el orden.

Riesgo: bajo. Columnas nullable, el home actual no las usa hasta que el servicio las lea.

---

## Contrato

`GET` home (`/{schema}/vendedor-app/home`), dentro de `ruta`:

```json
{
  "orden": "sugerido",
  "partida": {
    "latitude": -26.1775,
    "longitude": -58.1781,
    "direccion": "Depósito centro"
  },
  "items": [
    {
      "pdv_id": 10,
      "zona": "Norte",
      "zona_orden": 1,
      "orden_sugerido": 1,
      "latitude": -26.18,
      "longitude": -58.17
    }
  ]
}
```

`orden: "alfabetico"` y `partida: null` cuando no hay pin válido (falta lat o lng). `orden_sugerido` igual se manda, en el orden alfabético, para que Field tenga un solo criterio de sort.

---

## Plan de prueba en CI/CD

Pytest nuevo, función pura del orden (sin base):

- Tres PDV en una línea y el origen en el primero: el orden es a lo largo de la línea.
- Dos zonas: se recorre primero la del centroide más cercano al origen; el primer PDV de la segunda zona es el más cercano al último de la primera.
- Un PDV sin lat/lng queda último en su zona, después de los que sí tienen.
- Zona sin ninguna coordenada queda última, PDV por nombre.
- Sin origen: el orden es el nombre, `orden = alfabetico`.
- Empate de distancia: `pdv_id` menor primero.
- PATCH con latitud 120 responde 422.

Checks del PR en verde. Smoke de migración: la columna existe y es nullable en un schema de prueba. No hace falta test de UI de Field en CI; el orden es del backend.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`, field-app `3001`. Tenant `el_gigante` (o uno con zonas del día y algunas coordenadas).

1. Vendedor sin pin: en Field, “Mi Día” sigue en orden alfabético y no aparece un origen.
2. En la ficha del backoffice, cargar una dirección del centro de la ciudad y guardar. La ficha muestra lat/lng.
3. Recargar Field con el teléfono de ese vendedor: las zonas salen en bloques, no mezcladas. El primer comercio con mapa del primer bloque es el más cercano al pin (se puede contrastar abriendo el pin de Maps que Field ya tiene en la card).
4. Un comercio de esa zona sin coordenada aparece al final del bloque, no desaparece.
5. Borrar el pin: la lista vuelve al alfabeto.

---

## Criterios de aceptación

### AC-1 Con pin, el primero es el más cercano

- **Given** origen cargado y al menos dos PDV con coordenada en la zona más cercana.
- **When** se pide el home.
- **Then** `ruta.orden` es `sugerido` y el primer ítem con coordenada de `zona_orden = 1` es el de menor Haversine al origen.

### AC-2 Sin pin, alfabeto

- **Given** `partida_latitude` y `partida_longitude` nulos.
- **When** se pide el home.
- **Then** `ruta.orden` es `alfabetico` y los ítems salen por nombre como hoy.

### AC-3 Sin coordenada no se pierde

- **Given** un PDV del día sin lat/lng en una zona que sí tiene otros mapeados.
- **When** se pide el home.
- **Then** ese PDV está en la respuesta, en su zona, después de los mapeados.
