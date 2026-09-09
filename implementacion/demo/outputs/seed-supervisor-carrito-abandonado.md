# Seed — Supervisor Copilot (carrito abandonado)

Tenant: **demo**. SQL: `seed-supervisor-carrito-abandonado.sql`.

Re-ejecutable. Marca `sync_metadata.source = seed_supervisor_carrito_abandonado`.

## Qué deja cargado

10 clientes con:

- Pedido `estado = abierto`, origen `tienda`, 3 SKUs (prioridad Cofler) y total > 0.
- Envío HSM `hola_cliente_pedido` ~25 min antes del carrito, para que Lucía los vea en `funnel_clients` etapa `carritos`.

No crea etiqueta, grupo, plantilla ni agenda: eso es el ejercicio del Supervisor.

## Clientes

| id | Cliente | Zona |
|----|---------|------|
| 37010 | Almacén La Plata SRL | (sin zona) |
| 36814 | Almacén La Familia | Palermo |
| 36800 | Parrilla La Estancia | Palermo |
| 36798 | Almacén La Abundancia | Belgrano |
| 36804 | Carnicería El Corte Perfecto | Belgrano |
| 36803 | Almacén El Rincón | Belgrano |
| 36808 | Carnicería La Calidad | Colegiales |
| 36810 | Almacén La Esquina | Colegiales |
| 8 | Jorge Burkle | Villa Crespo |
| 36818 | Almacén La Nueva | Villa Crespo |

Etiqueta lista para asignar: **Carrito** (`demo.etiquetas.id = 19`, Pipeline CRM). Hoy no está asignada a nadie.

Plantillas ya existentes para reutilizar (no hace falta crear otra):

- `agente_agenda_recordatorio_pedido` (UTILITY)
- `estr_27_cart_open_234b97` (MARKETING, carrito abierto)
- `hola_cliente_pedido` (la del HSM de atribución)

## Prompt al Supervisor

> Armar un grupo de los que agregaron productos al carrito pero no cerraron pedido, revisar si sirve alguna plantilla (para no crear nuevas sin motivo), sino enviar a crear una y crear una nueva agenda para contactarlos y hacerles seguimiento en base a ese carrito.

Secuencia esperada:

1. Lucía lista la etapa carritos (~10 clientes) y etiqueta **Carrito**.
2. Lucía crea un grupo por esa etiqueta.
3. Sofía lista plantillas y reutiliza una de las de arriba (o abre el modal si no hay ninguna usable).
4. Martín crea la agenda HSM contra ese grupo + plantilla (confirmación).

## Cómo volver a sembrar

En Supabase (schema `demo`):

```sql
-- pegar el contenido de seed-supervisor-carrito-abandonado.sql
```

El `DO` borra la corrida anterior (pedidos/ítems/envíos marcados) y vuelve a insertar.
