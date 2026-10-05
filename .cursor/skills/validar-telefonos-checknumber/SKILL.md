---
name: validar-telefonos-checknumber
description: >-
  Use when bulk-validating phones already loaded for a distribuidora with
  checknumber.ai, or when the user mentions checknumber, ws_active, validar
  teléfonos, WhatsApp de la cartera, or a mass whatsapp_estado update on
  {schema}.clients.phone_number.
---

# Validar teléfonos con checknumber.ai

Chequeo pasivo de WhatsApp sobre los teléfonos ya cargados en `{schema}.clients`. No manda mensajes. El wizard de campañas (spec 089) es otro flujo: este skill cubre la cartera y los prospectos ya persistidos.

Script: `.cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py`

## Universo

Solo `{schema}.clients.phone_number` (cartera y prospectos). Quedan afuera `vendedores.telefono`, `campaign_prospect`, `conversations` y el ERP crudo.

## Antes de tocar nada

1. Confirmar `schema_name` si no está en el pedido.
2. Correr `self-test` y después `extraer`. Parar y mostrar el resumen.
3. `enviar` solo después de que la persona diga **confirmar envío**. Si `a_enviar` es 0, no hay llamada a la API: seguir a `aplicar` para copiar la caché vigente a los clientes.
4. `aplicar` solo después de que diga **confirmar carga**. Une `cache.csv` y `resultados.csv` (el resultado de esta corrida pisa la caché).

En el chat van conteos, costo y path del lote. No pegar la lista de teléfonos ni la API key.

## Comandos

Desde la raíz del repo, con `SUPABASE_DB_URL` en el pooler **6543** y `statement_cache_size=0` (el script ya lo fuerza). La key es `CHECKNUMBER_API_KEY` (env del backend, no del front).

```bash
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py self-test
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py extraer --schema SCHEMA
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py enviar --schema SCHEMA --lote RUTA --confirmar
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py bajar --schema SCHEMA --lote RUTA
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py aplicar --schema SCHEMA --lote RUTA
python .cursor/skills/validar-telefonos-checknumber/scripts/validar_telefonos.py aplicar --schema SCHEMA --lote RUTA --confirmar
```

`aplicar` sin `--confirmar` solo escribe el preview.

## Contrato

| Tema | Regla |
|---|---|
| Tarea | `ws_active` (la fila `core.phone_validation_provider` tiene que decir lo mismo). Trae WhatsApp, Business y días activos |
| API | `POST /v1/tasks` (archivo, un `+E.164` por línea) → `POST /v1/gettasks` hasta `exported` → bajar `result_url`. Header `X-API-Key` |
| Caché | `core.phone_whatsapp_check`, clave = dígitos. Vigente: 90 días si `sí`, 30 días si `no`. Esos no se reenvían |
| Precio | `price_per_check_usd` de esa fila. Hoy US$ 0,00018. Mostrar costo estimado y `GET /v1/balance` antes de enviar |
| Normalización | `54` con 12–13 dígitos se deja. 10 u 11 dígitos nacionales se prefijan con `54`. 11 dígitos que empiezan en `1` se dejan (NANP). El resto internacional de 11–15 dígitos se deja. Lo que no entra va a `invalidos.csv` y no se envía |
| Escritura en clients | `existente` o `no_existente` + `whatsapp_existencia_verificada_at`. Nunca `validado`. Nunca pasar `no_existente` → `existente` (Meta gana). Un `validado` no se toca |
| Caché al aplicar | Upsert de `has_whatsapp`, `is_business`, `active_days`, `provider_id=checknumber` |

## Salida

`implementacion/{schema}/outputs/checknumber/{stamp}/`

`resumen.json`, `input.txt`, `invalidos.csv`, `cache.csv`, `task.json`, `resultados.csv`, `aplicar-preview.csv`.

## Resumen para la persona

Después de `extraer`:

```text
Schema:
Clientes con teléfono:
Únicos E.164:
Inválidos:
Cache vigente:
A enviar:
Costo estimado USD:
Lote:
```

Preguntar **confirmar envío**. Después de `bajar`, sumar sí / no / sin resultado y `actual_amount`, y preguntar **confirmar carga**.

## Errores que frenan

- `401` key inválida. `402` sin saldo. `400` archivo o muy pocos números. `503` proveedor pausado: no se cobra, se puede reintentar el POST más tarde.
- `500` en el POST de alta: no reintentar. Puede haber quedado una tarea creada. Mirar `submit.json` y el dashboard.
- `status=failed` o 15 minutos sin `exported`: correr `bajar` de nuevo sobre el mismo lote. No crear otra tarea.
- Si `enviar` encuentra `task.json`, no reenvía.

## Fuera de este skill

No valida el directorio de una campaña (eso es el wizard de 089). No usa `ws_avatar`. No abre rama git: el lote vive en `implementacion/{schema}/`.
