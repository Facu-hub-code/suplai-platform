---
name: suplai-implementation-phase-10
description: Fase 10 pruebas E2E — Realiza un healthcheck de base de datos y corre las pruebas conversacionales automáticas con análisis de reportes de test.
---

# Fase 10 — Pruebas E2E y Healthcheck del Agente

Prerequisito: Todas las fases anteriores completadas exitosamente.

Esta fase actúa como puente directo hacia la skill principal de pruebas de extremo a extremo ([agent_e2e_testing](../../agent-e2e-testing/SKILL.md)).

## Pasos de Ejecución

1. **Lectura Obligatoria**:
   - El agente **debe leer obligatoriamente** la guía de uso detallada en [skill-guide.md](../../agent-e2e-testing/skill-guide.md) antes de ejecutar cualquier comando.
2. **Ejecutar Healthcheck de Base de Datos**:
   - Correr el script de validación (debería pasar exitosamente ya que todas las fases anteriores están completadas):
     ```bash
     python scripts/healthcheck_schema.py --schema {schema}
     ```
3. **Ejecutar Suite de Pruebas E2E**:
   - Confirmar si se prueba en modo vendedor o cliente, y lanzar la suite de 10 casos conversacionales:
     ```bash
     python scripts/test_agent_e2e.py --schema {schema}
     ```
4. **Auditoría de Reporte y Falsos Negativos**:
   - Abrir el archivo de reporte markdown generado en:
     `implementacion/{schema}/outputs/reporte_e2e_{timestamp}.md`
   - Realizar la validación crítica de los resultados, editando el markdown si hay falsos negativos marcados como `FAIL` de manera incorrecta por el auditor de OpenAI.

## Cierre

- `manifest.fases["10"].estado = cargado`
- `manifest.fases["10"].cargado_at = ISO Timestamp`
