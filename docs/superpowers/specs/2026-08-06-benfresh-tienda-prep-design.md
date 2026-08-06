# Spec: Preparación tienda Benfresh (prod-ready)

**Fecha:** 2026-08-06  
**Tenant:** `benfresh`  
**Estado:** diseño aprobado  
**Rama platform:** `feat/benfresh-tienda-prep`

## Objetivo

Dejar la **tienda web de Benfresh lista para producción**: catálogo con imágenes útiles, link de tienda post-pedido, origen `tienda` visible en Pedidos, PDV de prueba (Christian vía BENFRESH MARKET), y **base de clientes con teléfonos USA en formato correcto** marcados como WhatsApp `existente` (aún no validados por respuesta).

## Contexto (estado actual)

| Ítem | Hallazgo |
|------|----------|
| Christian | Vendedor `#4` (`549178640350466`); sigue como seller en WhatsApp |
| Teléfono PDV | `17864035046` hoy en cliente **DIXIE RIBS** `#13` |
| BENFRESH MARKET | `#11` con phone fake `9990000099911`, lista Default USD `#24` |
| `get_catalog_link` | Ya habilitada (opt-out; no está en `false`) |
| Imágenes | `0/202` productos con `image_url` |
| Flag catalog store | `metadata.catalog_store` ausente |
| `pedidos.origen` | Columna existe (default `suplai`); login-tienda no la setea; grilla Pedidos no la muestra |
| WhatsApp estados | 523 `no_validado`, 1 `existente` |
| Phones USA OK | **~278** con patrón `1` + 10 dígitos NANP (`^1[2-9]\d{9}$`), todos `no_validado` |
| Placeholders | ~207 con prefijo `99…` |
| Otros inválidos | ~39 (largo/prefijo raro, `54…`, etc.) |
| Verificación Meta | **No hay** lookup proactivo; solo inferencia al enviar o historial inbound |

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Objetivo | Tienda **prod-ready**, no solo demo Christian | El PDV de prueba es un caso; la red comercial necesita phones/estados coherentes | Solo setup de un teléfono de prueba |
| Formato phone | **USA E.164 digits:** `1` + área `[2-9]` + 9 dígitos (11 total) | Tenant Miami; casi nadie usa `54` | Criterio Argentina `54` |
| Mark `existente` | **A priori por formato** (bulk SQL/script) | Aún no hay envíos; no hay API Meta de “¿existe WA?” sin enviar | Verificar vía Meta contacts; solo CSV sin update |
| No tocar | Placeholders `99…`, inválidos, ya `validado` | Evitar falsos positivos y no degradar validados | Marcar todo el padrón |
| Timestamps | Setear `whatsapp_existencia_verificada_at = now()` al pasar a `existente` | Alineado a `set_estado_manual` / `marcar_por_envio` | Solo cambiar el enum |
| Christian PDV | Reusar `#11` + phone `17864035046` + lista `#24`; liberar `#13` | Match exacto login-tienda; Christian sigue seller | Desactivar vendedor |
| Tool link | No tocar `get_catalog_link` | Ya disponible | Forzar key en `tools_habilitadas` |
| Link post-pedido | Flag `catalog_store.append_link_after_order_tools=true` | Spec 026 ya implementado | Reescribir copy v1 |
| Imágenes | Top 100 + match nombre + **hotlink** benfreshfood.com | Mejora visual rápida | Supabase Storage |
| Origen tienda | `origen='tienda'` al **crear** carrito en login-tienda | Ver canal desde el carrito abierto | Solo al confirmar |
| UI origen | Badge (+ filtro) en `pedidos-table` | Operación diaria en Pedidos | Solo ERP raw |
| Paso a `validado` | **Manual** tras el primer envío real (operador) | Aún no hay campañas/envíos; el humano valida con evidencia de envío/respuesta | Hook automático en inbound |

## Alcance

### Incluido (v1)

1. **Higiene teléfonos Benfresh**
   - Script/SQL dry-run: listar candidatos USA OK vs inválidos/fake.
   - `--apply`: `whatsapp_estado = 'existente'` + `whatsapp_existencia_verificada_at = now()` para phones que matchean `^1[2-9]\d{9}$` y estado actual ∈ (`no_validado`, `NULL`) — **no** pisar `validado` / `no_existente` salvo regla explícita.
   - No inventar ni reescribir `phone_number` en este paso (salvo el caso Christian `#11`/`#13` abajo).
2. **Ops PDV Christian:** phone en `#11`, liberar `#13`, flag `catalog_store` en metadata.
3. **Script imágenes** `scripts/benfresh/scrape_benfresh_images.py` (dry-run CSV + `--apply` hotlink).
4. **Backend:** INSERT carrito con `origen='tienda'`; `p.origen` en pedidos v2.
5. **Backoffice:** badge origen (+ filtro) en Pedidos.

### Fuera de alcance

- Lookup proactivo Meta “contacts” (no disponible / no implementado).
- Envío masivo de plantillas para inferir existencia.
- Subir imágenes a Storage.
- Normalizar todos los phones (agregar `1` faltante, limpiar `54`, etc.) — solo reporte en dry-run; corrección masiva de dígitos es follow-up.
- Cambiar copy del segundo mensaje (spec 026).
- Tocar cliente `#50`.
- Cambiar resolución seller/client WhatsApp de Christian.
- Backfill `origen` en pedidos históricos.
- Auto-marcar `validado` al recibir inbound (queda validación manual post-primer envío).

## Orden de implementación

| Orden | Repo | Rama sugerida | Dependencia |
|-------|------|---------------|-------------|
| 1 | `suplai-platform` | `feat/benfresh-tienda-prep` | Spec + script imágenes + script higiene WA |
| 2 | Ops BD | dry-run → apply higiene + cliente `#11`/`#13` + flag | Tras review CSV |
| 3 | `backend-supabase` | `feat/benfresh-tienda-origen` | Antes que UI filtro |
| 4 | `product-management-app` | `feat/benfresh-tienda-origen-ui` | Consume `origen` v2 |
| 5 | Apply imágenes | `--apply` | Tras dry-run revisado |

Merge: **backend → backoffice**; ops/scripts en paralelo.

## Migración de base de datos

**Sin migración de BD (DDL).**

- Datos: UPDATE `clients.whatsapp_*` (bulk formato USA); UPDATE phones `#11`/`#13`; merge `distribuidoras.metadata`; UPDATEs `productos.image_url`; INSERT futuros con `origen='tienda'`.

**Rollback / riesgo**

- WA: guardar CSV pre-apply (`id`, `phone`, `estado_prev`); revertir a `no_validado` si hace falta.
- Marcar `existente` por formato **no garantiza** que el número tenga WhatsApp; el primer envío real puede pasar a `no_existente` vía `marcar_por_envio`.
- Cliente / flag / imágenes / origen: igual que antes.

## Plan de prueba en CI/CD

| Repo | Qué validar |
|------|-------------|
| platform | Scripts: dry-run sin apply; args; fallo claro sin DB URL; regex USA unit-testable |
| backend | Test insert carrito `origen='tienda'`; checks verdes |
| backoffice | Lint; badge origen si hay test |
| Gap | E2E tienda+WA no en pipeline → checklist humana |

## Plan de prueba humana (antes del PR / apply prod)

**Servicios:** backend `8000`, backoffice `3000`, tienda ≠ 3000.

**Checklist**

1. [ ] Dry-run higiene: ~278 candidatos USA; fakes `99` e inválidos listados aparte.
2. [ ] Apply higiene: esos quedan `existente` + timestamp; `validado` previos intactos (si hubiera).
3. [ ] `#11` con `wp=17864035046` + lista Default; Dixie sin ese phone; login tienda OK.
4. [ ] Carrito nuevo `origen='tienda'`; badge/filtro en Pedidos; agente sigue `suplai`.
5. [ ] Flag catalog store: PDV cliente recibe segundo mensaje con URL post create/edit.
6. [ ] Imágenes: dry-run → apply → tienda muestra fotos en top productos.

## Criterios de aceptación

- **AC-1:** `#11` phone `17864035046` + lista `#24`; `#13` sin ese phone.
- **AC-2:** Flag `catalog_store.append_link_after_order_tools === true`.
- **AC-3:** `get_catalog_link` sin regresión.
- **AC-4:** Script imágenes dry-run + apply (hotlinks absolutos).
- **AC-5:** Nuevo carrito login-tienda → `origen='tienda'`.
- **AC-6:** Pedidos v2 + UI muestran/filtran origen.
- **AC-7:** Clientes con phone USA `^1[2-9]\d{9}$` y estado `no_validado` pasan a `existente` con `whatsapp_existencia_verificada_at` seteado; placeholders/inválidos no se marcan `existente` solo por este job.

## Archivos clave (referencia)

- `backend/services/tienda_login.py` — INSERT pedido abierto
- `backend/services/whatsapp_cliente_estado_service.py` — estados WA
- `backend/routers/pedidos.py` — SELECT v2
- `backoffice/components/pedidos-table.tsx` — badge/filtro
- `agent/app/agent/tools/catalog_store_promotion.py` — ya implementado
- `scripts/benfresh/scrape_benfresh_images.py` — a crear
- `scripts/benfresh/backfill_whatsapp_existente_usa.py` (o SQL) — a crear
- Sitio: `https://www.benfreshfood.com` (`assets/images/product/*`)
