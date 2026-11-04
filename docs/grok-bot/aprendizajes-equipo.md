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
- **Por qué:** es una de las lecciones de la retrospectiva de P3. Un dato raro reportado sin mirar el crudo puede ser un campo mal leído o un filtro de más, y genera trabajo para la distribuidora y para Faka.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (DEV-257)

### A2. No dar algo por hecho si falta verificarlo

- **Fecha:** 2026-11-04
- **Para:** Todos
- **Regla:** algo está hecho solo si se comprobó después de hacerlo (un `SELECT` después de escribir, el embedding al día después de re-vectorizar, la respuesta del agente en la prueba). Si no se pudo comprobar, se reporta como "hecho, sin verificar" y se dice qué faltó.
- **Por qué:** es una de las lecciones de la retrospectiva de P3. Un cierre falso cuesta más que un pendiente declarado.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (DEV-257)

### A3. Declarar qué tenants toca cada cosa

- **Fecha:** 2026-11-04
- **Para:** Todos
- **Regla:** cada tarea, propuesta, archivo y comentario de cierre dice para qué tenants vale y cuáles no se tocaron. Nada de "en todos" sin listarlos.
- **Por qué:** es una de las lecciones de la retrospectiva de P3. Sin el alcance declarado, un cambio pensado para un tenant puede alcanzar a otros y un número no se puede revisar.
- **Sale de:** retrospectiva de P3 · Integraciones ERP v3, sección 9 (DEV-257)
