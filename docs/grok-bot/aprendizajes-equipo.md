# Aprendizajes del equipo de Grok Bot

Reglas de proceso que salen de revisar el trabajo del equipo. Las escribe la sesión padre de Claude (P-DEV-3) por PR y rigen desde que Faka las mergea en `main`. El Jefe lee este archivo cada día junto con [protocolo-claude.md](protocolo-claude.md) y se las pasa a los bots que corresponda.

Solo van acá los aprendizajes de **proceso** (cómo trabajar). Los del tenant (cómo nombra sus productos, qué no se ofrece) van en `core.aprendizajes`.

## Cómo se agrega uno

Al final de la lista, con el número siguiente. No se borran: si una regla cambia, se agrega una nueva que dice a cuál reemplaza.

```
### A{n}. {regla en una línea}

- **Fecha:** AAAA-MM-DD
- **Para:** Jefe, Vigía, Catálogo, Probador o Todos
- **Regla:** qué hacer, concreto.
- **Por qué:** el caso que la motivó, con números si los hay.
- **Sale de:** DEV-{n} (issue o comentario `Corrección:`)
```

---

### A1. Antes de reportar un dato raro, leer el valor crudo

- **Fecha:** 2026-11-04
- **Para:** Todos
- **Regla:** si un número o un campo llama la atención (stock negativo, precio en 0, una descripción vacía, un conteo que no cierra), mirar el valor crudo en la tabla de origen con un `SELECT` puntual antes de reportarlo. En el reporte, poner el valor crudo y la consulta.
- **Por qué:** en gonzales se leyó que el teléfono de un vendedor era "20", su código. En la base el valor era el placeholder `erp-20`: solo se habían mirado los dígitos. Se abrió una issue por un falso positivo, que terminó en un PR preventivo (#452) en vez de en un arreglo.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (DEV-241)

### A2. No dar algo por hecho si falta verificarlo

- **Fecha:** 2026-11-04
- **Para:** Todos
- **Regla:** algo está hecho solo si se comprobó después de hacerlo (un `SELECT` después de escribir, el embedding al día después de re-vectorizar, la respuesta del agente en la prueba). Si no se pudo comprobar, se reporta como "hecho, sin verificar" y se dice qué faltó. Una issue no pasa a In Review ni a Done mientras un comentario propio diga que falta verificar algo: primero se verifica y se comenta el resultado.
- **Por qué:** una issue pasó a Done a las 09:21, y su propio comentario de las 09:25 decía "sigue abierta hasta verificar la ventana de las 12 UTC". No quedó registro de esa verificación. Un cierre falso cuesta más que un pendiente declarado.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (DEV-242)

### A3. Declarar qué tenants toca cada cosa

- **Fecha:** 2026-11-04
- **Para:** Todos
- **Regla:** cada tarea, propuesta, archivo y comentario de cierre lista **todos** los tenants afectados, no solo el objetivo, con cuántas filas cambian en cada uno. Si alcanza a un tenant que no estaba en la tarea, se anuncia como efecto fuera de alcance antes de hacerlo. Nada de "en todos" sin listarlos.
- **Por qué:** el PR #450 cambió el texto `{vendedor}` de los mensajes en benfresh (24 clientes), del_corro (111) y el_gigante (114), aunque el proyecto decía "dimer, GEV como referencia" y benfresh estaba afuera. El PR #455 vació `clients.vendedor` en 115 clientes de el_gigante. Los dos tuvieron vista previa y OK, pero nadie los anunció como efectos fuera de alcance.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (PR #450 y #455)
