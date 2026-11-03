---
name: suplai-catalogo-novedades
description: >-
  Use when the Catálogo bot completes new products of dimer, almaro or
  gonzales so the sales agent can find them: product photo, commercial
  description, aliases and category, then re-vectorize. Works from the
  Vigía's daily file.
when-to-use: catálogo, novedades, foto, descripción, alias, categoría, vectorizar
---

# Catálogo de novedades

Dejás listas las novedades que encontró el vigía: foto, descripción, alias y categoría, y después re-vectorizás. Stock y precio no son tuyos: los trae el ERP.

## Modo de escritura

**Leé primero la issue DEV-208 en el reporte del jefe.** Hasta que diga qué opción se eligió, trabajás en **modo propuesta**:

- No escribís en la base.
- Guardás lo que cargarías en `~/suplai-bots/propuestas/{AAAA-MM-DD}-{schema}.json`, una fila por producto con el antes y el después.
- El jefe le muestra una muestra a Faka.

Las plantillas de abajo valen solo si DEV-208 eligió la opción 1 (SQL por el MCP de Supabase).

## Entradas

- `~/suplai-bots/novedades/{AAAA-MM-DD}-{schema}.json`, que deja el vigía.
- Trabajá solo las filas con `en_catalogo` verdadero. Empezá por las que tienen stock.
- Orden de tenants: `almaro`, `gonzales`, `dimer`.

## Cómo completar cada campo

**Foto**
- Tiene que ser el producto exacto: misma marca, variedad y presentación (gramos y unidades por pack). Fondo blanco, sin marca de agua ni collage.
- Fuentes para almaro y gonzales: `arcorencasa.com` y `tokin.vtexassets.com`, que ya se usan. Para dimer: `dimerltda.cl` o supermercados chilenos (Jumbo, Lider, Unimarc).
- Si no estás seguro de que es el mismo producto, no la cargues: dejale al jefe la pregunta con 2 o 3 candidatos y el link de cada uno.
- Combos: no les busques foto. Anotalos.

**Descripción**
- Una frase o dos con categoría, marca y línea, variedad y presentación, y unidades por bulto o display si están en la ficha.
- Sin inventar sabores, formatos ni atributos que no estén en el nombre, la ficha o la foto oficial. Expandí las abreviaturas del ERP solo si estás seguro (`CAR` → caramelo, `BAR` → barra).
- almaro y gonzales: seguí `implementacion/almaro/config.json` → categoría primero, marca o línea (Cofler, Bon o Bon, Rocklets), sin inventar.
- Combos de GEV: describí qué trae el combo en palabras ("Combo de 6 barras de cereal Cereal Mix Pro de yogur y frutilla y 6 de chocolate, con exhibidor chico").

**Alias**
- De 3 a 6 por producto, en minúsculas: marca, línea, nombre coloquial y sinónimos de la categoría ("rocklets", "confites de chocolate", "lentejas de chocolate").
- Sin códigos ni precios.

**Categoría**
- Solo una categoría que ya exista en `{schema}.categorias`. No crees categorías nuevas: si ninguna sirve, preguntale al jefe.

## Plantillas de escritura (solo con DEV-208 = opción 1)

Reglas: una sentencia por campo y por lote de hasta 50 productos. Siempre con el schema explícito y con la condición que evita pisar lo que cargó un humano. Antes y después, un `SELECT` de las mismas filas, que va al reporte.

```sql
-- Foto: solo si no tiene
update {schema}.productos set image_url = '{url}', updated_at = now()
where product_code = '{codigo}' and coalesce(image_url, '') = '';

-- Descripción: solo si sigue siendo la que leíste (vacía, igual al nombre o "Combo GEV [")
update {schema}.productos set descripcion = $d${descripcion}$d$, updated_at = now()
where product_code = '{codigo}' and coalesce(descripcion, '') = $a${descripcion_anterior}$a$;

-- Alias: alias_norm igual que el backend (minúsculas, sin tildes, solo letras y números)
insert into {schema}.productos_aliases (alias_norm, alias_raw, product_code, weight, created_at, updated_at)
select regexp_replace(translate(lower(v.raw), 'áéíóúüñ', 'aeiouun'), '[^a-z0-9]', '', 'g'), v.raw, '{codigo}', 1, now(), now()
from (values ('{alias_1}'), ('{alias_2}')) as v(raw)
on conflict (alias_norm, product_code) do nothing;

-- Categoría: solo ids que existen
insert into {schema}.product_categories (product_code, categoria_id)
select '{codigo}', id from {schema}.categorias where id = {categoria_id}
on conflict do nothing;
```

**Prohibido:** `DELETE`, `TRUNCATE`, `DROP`, `ALTER`, `CREATE`, `apply_migration`, cualquier tabla que no sea de las cuatro de arriba, tocar `stock`, `nombre`, `en_catalogo`, precios o listas, y cualquier `UPDATE` sin `product_code` en el `WHERE`.

**Re-vectorizar:** la base no lo hace sola. Después de cada lote, `POST https://web-production-f544f.up.railway.app/{schema}/productos/vectorize` con el body `["codigo1", "codigo2", ...]`. Devuelve `{"status": "ok", "scheduled": N}`. Al día siguiente, el vigía confirma que el embedding quedó al día.

## Resumen para el jefe

Por tenant: cuántas revisaste, cuántas fotos, descripciones, alias y categorías cargaste (o propusiste), los códigos re-vectorizados y la lista de las que no pudiste resolver con el motivo y la pregunta concreta para Faka.
