# Guía de pruebas — {TITULO}

**Feature:** `{SLUG}`  
**Fecha:** {FECHA}  
**Specs:** {SPECS}  
**Repos / ramas:** {REPOS_RAMAS}

---

## 1) Resumen (30 segundos)

{RESUMEN}

---

## 2) Qué levantar en localhost

| Servicio | Repo | Rama | Comando | URL |
|----------|------|------|---------|-----|
| Backend API | `backend/` | `{RAMA_BACKEND}` | `uvicorn main:app --reload --port 8000` | http://localhost:8000 |
| Backoffice | `backoffice/` | `{RAMA_BACKOFFICE}` | `BACKEND_URL=http://localhost:8000 npm run dev` | http://localhost:3000 |
| Field app | `field-app/` | `{RAMA_FIELD}` | `BACKEND_URL=http://localhost:8000 npm run dev -- -p 3001` | http://localhost:3001 |

**Variables de entorno mínimas**

- Backend: `SUPABASE_DB_URL` (puerto **6543**, pooler transaccional)
- Frontends: `BACKEND_URL=http://localhost:8000`

---

## 3) Pre-checks (antes de probar UI)

- [ ] Migraciones aplicadas: {MIGRACIONES}
- [ ] Tenant de prueba activo con `{FLAG}` = true
- [ ] Backend responde: `GET http://localhost:8000/docs`
- [ ] Tests unitarios pasan en repos tocados
- [ ] {OTROS_PRECHECKS}

### SQL de smoke (tenant `{SCHEMA}`)

```sql
-- Copiar/pegar en Supabase SQL editor o MCP execute_sql (solo lectura salvo UPDATE flag)
{SQL_PRECHECKS}
```

---

## 4) Datos que tienen que existir

| Dato | Dónde | Por qué |
|------|-------|---------|
| {DATO_1} | {TABLA/UI} | {RAZON} |

**Cómo prepararlos si faltan**

1. {PASO_DATOS}

---

## 5) Mapa de pantallas (navegación)

### Backoffice

| # | Ruta / sección | Qué validar |
|---|----------------|-------------|
| 1 | `{RUTA}` | {VALIDACION} |

### Field app

| # | Ruta | Qué validar |
|---|------|-------------|
| 1 | `/{schema}/home` | {VALIDACION} |

---

## 6) Casos de prueba

### CP-01 — {NOMBRE} (happy path)

**Precondición:** {PRECONDICION}  
**Pasos:**

1. {PASO}
2. {PASO}

**Resultado esperado:** {RESULTADO}

### CP-02 — {NOMBRE}

...

---

## 7) Criterios de aceptación (checklist final)

- [ ] {CRITERIO}

---

## 8) Troubleshooting

| Síntoma | Causa probable | Fix |
|---------|----------------|-----|
| {SINTOMA} | {CAUSA} | {FIX} |

---

## 9) Audio

- Guion hablado: `output/{SLUG}/guide-audio.txt`
- Audio: `output/{SLUG}/guide-audio.m4a`

Reproducir:

```bash
.cursor/skills/feature-test-guide/scripts/play-guide-audio.sh \
  .cursor/skills/feature-test-guide/output/{SLUG}/guide-audio.m4a
```
