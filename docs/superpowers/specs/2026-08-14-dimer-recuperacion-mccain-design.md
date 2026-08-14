# Dimer — recuperación de clientes perdidos de papas McCain

Fecha: 2026-08-14
Schema: `dimer`
Estado: diseño aprobado, pendiente de aplicación

## Objetivo

Preparar una primera campaña de recuperación para 30 clientes perdidos de papas McCain:

1. Personalizar la plantilla Meta `prueba_01` con un nombre de pila confiable.
2. Mejorar el reconocimiento de la jerga comercial de papas congeladas para restaurantes (`7`, `10`, `12`, `kilo con IVA`).
3. Permitir que el agente ofrezca alternativas equivalentes cuando el motivo de abandono sea precio, sin asumirlo de antemano.
4. Programar un envío puntual para el lunes 17 de agosto de 2026 a las 10:00 de Chile.

## Alcance explícito

### Incluido

- Reemplazar los 10 miembros actuales de `Grupo 1` por 30 personas naturales con teléfono móvil chileno válido.
- Completar `dimer.clients.nombre_de_pila` para esos 30 clientes.
- Mantener el grupo dinámico por la etiqueta existente `Grupo 1` (`etiqueta_id = 2`).
- Agregar alias inequívocos para las papas McCain de 7, 9/10 y 12 mm, además de sus variantes.
- Completar pesos estructurados para describir el formato comercial: cantidad de bolsas por caja y peso de cada bolsa.
- Agregar al contexto del agente reglas de jerga, equivalencias de milímetros y precio final con IVA.
- Crear una agenda puntual, activa, para `prueba_01` y `Grupo 1`.
- Generar artefactos locales de preview antes de escribir y verificar los resultados después de la carga.

### Fuera de alcance

- Integración con Odoo para comprobar si los clientes siguen comprando otros productos.
- Automatizar la clasificación del motivo de abandono.
- Crear descuentos o modificar listas de precios.
- Alterar el texto de la plantilla Meta `prueba_01`.
- Enviar mensajes manualmente durante la configuración.
- Modificar otros tenants o grupos de Dimer.

## Diseño funcional

### Grupo de recuperación

El grupo actual contiene empresas sin nombre de pila y un contacto de prueba. Se reemplazará su membresía por 30 personas naturales seleccionadas conservadoramente:

- teléfono normalizado con formato móvil chileno `569` + 8 dígitos;
- nombre legal que permita inferir un nombre de pila con alta confianza;
- `activo_ai IS NOT false`;
- sin empresas, sociedades ni contactos Suplai.

La plantilla solicita la variable `nombre`. El enviador de agenda ya prioriza `nombre_de_pila` cuando esa variable está presente, por lo que no se cambiará código de backend.

### Jerga y equivalencias

- `7`, `7mm` y `kilo de 7` significan corte de 7 mm.
- `10`, `10mm` y `kilo de 10` pueden corresponder a una caja rotulada 9 o 10 mm.
- `12`, `12mm` y `kilo de 12` pueden corresponder a una caja rotulada 11 o 12 mm.
- `tipo McDonald's` se interpreta como referencia de estilo al corte McCain Fast Food de 7 mm, sin afirmar proveedor ni equivalencia exacta.
- Si existen varias opciones, el agente presenta primero McCain y aclara el milimetraje impreso en la caja.
- Solo ofrece otra marca por precio cuando el cliente confirma que esa es la objeción o solicita una opción económica.

### Consultas por kilo e IVA

Los precios de Dimer se consideran finales en CLP con IVA incluido. El agente no debe sumar IVA.

En la jerga de estos clientes, “precio por kilo”, “kilo con IVA” o “¿a cuánto está el kilo de 7 mm?” identifica el tipo de papa y solicita una cotización comercial. No exige cotizar exactamente `1 kg`.

El agente responderá con:

- producto y corte reconocido;
- precio vigente de la unidad mínima de venta, final con IVA;
- cantidad de bolsas de la caja;
- peso de cada bolsa.

Para obtener esos datos, el prompt y los overrides por tenant de `tools_descripciones` ordenarán la secuencia `search_products → get_product_by_code`: la primera tool resuelve el SKU y el precio; la segunda entrega `unidades_por_bulto` y `peso_referencia_kg`. El agente no inferirá el formato desde el nombre del producto ni desde su memoria. Esto no requiere modificar código del runtime.

Ejemplo: “Tenemos PAPAS MCCAIN FAST FOOD 8×2,25 KG 7MM. La caja trae 8 bolsas de 2,25 kg y sale $33355 CLP final, IVA incluido.”

No se calculará ni persistirá un precio por `1 kg`. Si el cliente indica que necesita una cantidad de kilos, el agente explicará el formato disponible y preguntará cuántas cajas o unidades quiere, sin convertir automáticamente kilos a bolsas.

`peso_referencia_kg` representa el peso de una bolsa y `unidades_por_bulto` la cantidad de bolsas de la caja. Estos productos permanecerán con `es_pesable=false`: son presentaciones cerradas, no mercadería fraccionada o pesada al preparar el pedido.

## Decisiones de diseño técnico

| Decisión | Motivo | Alternativa descartada |
|---|---|---|
| Reemplazar la membresía del grupo | Los 10 actuales no cumplen el requisito de personalización y contienen un contacto de prueba | Mantenerlos y sumar 20 produciría un grupo de 30 con mensajes poco humanos o incorrectos |
| Usar `nombre_de_pila` | El enviador ya lo prioriza para la variable `nombre` de Meta | Sobrescribir `nombre` o `razon_social` destruiría el nombre legal |
| Alias genérico con SKU principal | Evita que un mismo alias normalizado apunte ambiguamente a varios productos | Duplicar `kilo de 7` en dos SKUs puede volver no determinística la búsqueda |
| Equivalencia comercial ±1 mm en el prompt | Refleja cómo compran los restaurantes y cómo viene rotulada la caja | Renombrar productos ocultaría la medida real del fabricante |
| Cotizar el formato comercial sin dividir por kg | Coincide con la forma de venta de Dimer y evita cálculos innecesarios o cantidades asumidas | Derivar y comunicar un valor por 1 kg no representa la unidad mínima de venta |
| Exigir `get_product_by_code` después de buscar | `search_products` no expone hoy peso y unidades por bulto; el segundo lookup los entrega estructurados sin cambiar runtime | Inferir el formato desde el nombre o depender de memoria produce respuestas menos confiables |
| Mantener `es_pesable=false` | Cada SKU se vende en bolsas/cajas cerradas; el peso solo describe la presentación | Activarlo habilitaría conversiones de fracciones destinadas a mercadería de peso variable |
| Agenda puntual | Esta es una primera campaña controlada, no una recurrencia | Una agenda recurrente podría reenviar la plantilla sin una nueva aprobación |

## Datos aprobados

### Alias principales

- McCain Fast Food 7 mm (`110A74011`): `kilo de 7`, `papa 7`, `papas 7mm`, `tipo mcdonalds`.
- McCain Corte Fino 7 mm (`110A11121`): `corte fino 7`, `papa fina 7mm`, `mccain fina`.
- McCain Tradicional 9 mm (`110111091`): `kilo de 10`, `papa 10`, `papas 10mm`, `tradicional 10mm`.
- McCain Corte Casero 12 mm (`110113101`): `kilo de 12`, `papa 12`, `papas 12mm`, `corte casero 12`.
- Alias específicos adicionales para Surecrisp, Crinkle, Duquesas y Smiles.

### Agenda

- Plantilla: `prueba_01`.
- Grupo: `Grupo 1`.
- Tipo: `puntual`.
- Fecha: `2026-08-17`.
- Hora deseada en Chile: `10:00`.
- Hora persistida: `11:00`, porque el backend productivo usa el fallback global `America/Argentina/Buenos_Aires` (UTC−3) y Chile estará en UTC−4.
- Estado: activa.

## Orden de implementación

1. Generar CSV de preview con los 30 clientes, nombres de pila y membresía objetivo.
2. Generar CSV de alias y pesos de presentaciones.
3. Actualizar el JSON local de prompt de Dimer con el bloque aprobado.
4. Revisar artefactos y conteos.
5. Aplicar en una transacción acotada a `dimer`:
   - nombres de pila;
   - membresía de etiqueta `Grupo 1`;
   - pesos estructurados;
   - alias;
   - contexto del tenant;
   - agenda puntual.
6. Verificar con una consulta consolidada.

No hay dependencias cross-repo ni múltiples PR. La entrega vive en `suplai-platform`, rama `feat/dimer-mccain-recovery`.

## Migración de base de datos

Sin migración de BD. Se actualizan datos existentes en:

- `dimer.clients`
- `dimer.clientes_etiquetas`
- `dimer.productos`
- `dimer.productos_aliases`
- `dimer.agenda`
- `public.distribuidoras.contexto`
- `public.distribuidoras.tools_descripciones`

Riesgo principal: una membresía o nombre incorrecto genera mensajes mal personalizados. Mitigación: preview aprobado, transacción y verificación exacta.

## Criterios de aceptación

- `Grupo 1` contiene exactamente 30 clientes.
- Los 30 tienen `nombre_de_pila` no vacío y teléfono móvil chileno válido.
- Emilio Ballistreri/Suplai y las empresas del grupo anterior quedan fuera.
- `prueba_01` conserva `variable_columns = ["nombre"]`.
- Los alias `kilo de 7`, `kilo de 10` y `kilo de 12` resuelven al SKU principal acordado.
- Las presentaciones alcanzadas tienen `unidades_por_bulto` y `peso_referencia_kg` consistentes con el nombre del producto, y conservan `es_pesable=false`.
- El contexto explica milímetros, tolerancia de 1 mm, IVA incluido, cotización por formato sin división por kg y estrategia de recuperación.
- El contexto exige `search_products → get_product_by_code` antes de informar cantidad y peso de bolsas.
- Los overrides por tenant de ambas tools refuerzan el mismo contrato sin alterar otros tenants.
- Existe una sola agenda puntual activa para `Grupo 1` + `prueba_01` el 2026-08-17 a las 11:00 del reloj operacional del backend, equivalente a las 10:00 de Chile.
- No se modifican precios, plantillas Meta ni datos de otros tenants.

## Plan de prueba en CI/CD

Es una carga de datos y configuración sin cambios de runtime:

- validar sintaxis y conteos de los CSV;
- validar JSON del prompt;
- ejecutar consultas post-carga para grupo, nombres, alias, pesos y agenda;
- comprobar que no existan alias normalizados duplicados con distinto SKU;
- comprobar idempotencia lógica: una nueva ejecución no debe duplicar membresías, alias ni agenda.

Gap actual: no existe un pipeline CI que replique datos productivos de tenant. El mínimo aceptable es preview local versionado y verificación de solo lectura contra Supabase después de la transacción.

## Plan de prueba humana antes del PR

- [ ] Levantar backend en `8000`.
- [ ] Levantar backoffice en `3000` con `BACKEND_URL=http://localhost:8000`.
- [ ] Ingresar al tenant `dimer`.
- [ ] Abrir Grupos y confirmar que `Grupo 1` muestra 30 clientes.
- [ ] Revisar una muestra de nombres: Luisa, Juan, Agustín, Mónica, María y Verónica.
- [ ] Abrir Agenda y confirmar `prueba_01`, fecha 17/08/2026, hora operacional 11:00 y estado activo.
- [ ] Confirmar que 11:00 Argentina equivale a 10:00 Chile el 17/08/2026.
- [ ] En laboratorio del agente consultar: `¿A cuánto está el kilo de 7mm?`.
- [ ] Confirmar que responde con McCain Fast Food 7 mm, precio final de caja con IVA, `8 bolsas de 2,25 kg` y SKU real, sin calcular un valor por 1 kg.
- [ ] Consultar `Necesito 20 kilos de 7mm` y confirmar que explica el formato y pregunta cuántas cajas o unidades quiere, sin convertir kilos a bolsas.
- [ ] Consultar `¿Tenés papa de 10?` y verificar que reconoce McCain Tradicional 9 mm como equivalencia comercial.
- [ ] Decir `dejé de comprar porque está muy cara` y verificar que ofrece una alternativa equivalente más económica.
- [ ] Dar un motivo distinto a precio y verificar que no fuerza una alternativa barata.

## Rollback

Antes de aplicar se conservará un snapshot de:

- membresía actual de `Grupo 1`;
- `nombre_de_pila` de los clientes afectados;
- alias existentes de los SKUs alcanzados;
- valores de peso actuales;
- contexto actual;
- ausencia/presencia de agenda equivalente.

El rollback restaura esos valores y elimina únicamente la agenda creada por esta entrega.
