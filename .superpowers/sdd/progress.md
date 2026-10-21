# SDD Progress — Copilot agentes especialistas

- Plan: docs/superpowers/plans/2026-09-08-copilot-agentes-especialistas.md
- Spec: docs/specs/038-copilot-agentes-especialistas.md
- Branches: feat/copilot-agentes-especialistas (platform already; backend/backoffice to create)

Task 1: complete (commits 850c55f..1a3f855, review clean; minor: nl_sql exclusion test only on audiencia)
Task 2: complete (commits 1a3f855..81819cd, review clean after rename 118)
Task 3: complete (commits 81819cd..ae1d873, review Important deferred to Task 4/5: list/orchestrator slug)
Task 4: complete (commits ae1d873..10240c6, review 409 HTTP deferred to Task 5 as planned)
Task 5: complete (commits 10240c6..dfb1f3a, review: empty-string 422 via Pydantic accepted; whitespace 400 fixed)
Task 6: complete (commits 1926771..41dc322, review clean after rename no-op fix)
Task 7: complete (backend 6877412, front 7e7a68f..fd8c81e, race guard added; no FE unit tests)
Task 8: complete (commits 6877412..03dd708, review clean after honest-dates fix; minor: filtro_fecha_aplicado false always on no-date stages)
Task 9: complete (backend 03dd708..982842b, front fd8c81e..1dd44eb; review after heuristic isolation; minor: tests allow nl_sql future fallback)
Task 10: complete (commits 982842b..c9c7aca, review after orchestrator copy; minor: "timezone" in compose vs "Zona horaria" in preview)
Task 11: complete (commits c9c7aca..757e384, review after latest last_sync_at; documents parity with HTTP diagnostico deferred per plan one-liner)
Task 12: complete (platform 757b663..f736df7, review after docs alignment; E2E evals blocked — no tests/copilot_evals; tsc pre-existing red)
Final-review fix: complete (backend 0b34e87 Omar chips+Carlos prompt+pack tests; front 0b3f200 stale list race; re-review approved)


# SDD Progress — ETL alta catálogo

- Plan: docs/superpowers/plans/2026-10-21-etl-alta-catalogo.md
- Spec: docs/specs/128-etl-alta-catalogo.md
- Backend: /Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase branch feat/erp-alta-catalogo-automatica base 87b44d5
- Platform: feat/erp-alta-catalogo-automatica

Task 1: complete (commits 87b44d5..e4e9e52, review clean)
Task 2: complete (commits e4e9e52..1ff329e, review clean; minor: fixture path depends on cwd, PLAYBOOKS untested, conversion param hints)
Task 3: complete (commits 1ff329e..455c966, review clean; minor: escrito asserts omit upd/caja, alias cap and empty description untested, precio hueco duplicated)
Task 4: complete (commits 455c966..08f9676, review clean)
Task 5: complete (commits 08f9676..6a318a2, review clean; minor: no 200 test, tenant SELECTs live in the service adapter)
Task 6: complete (commits 6a318a2..1560b7f, review clean; minor: leer_faltantes marked read-only though it claims; tool imports the router adapter)
Task 7: complete (commits 1560b7f..1ac0ee9, review clean after releasing a claimed row)
Task 8: complete (platform b651081, review clean; follow-up: README still points the bot only at Supabase MCP, spec 127 body still describes the category queue)
Deprecado el 2026-10-21: el job no llama al worker. La categoría volvió al alta del spec 127.
