# Casos reales — Benfresh

Fixtures provistos por el distribuidor para validar el flujo **vendedor → teléfono central → carga automática**.

## Estructura

```
casos-reales/
  manifest.json      # perfil seller, sequential, teléfono de prueba
  contexto.md        # narrativa del caso de uso (lo lee el agente al expandir)
  casos/
    NN-slug/
      caso.json      # metadatos y expectativas
      mensaje.txt    # texto que se envía al webhook
      mensaje_simulado.txt  # opcional: salida simulada de visión/OCR
      imagen.*       # opcional: referencia visual (no se sube al webhook v1)
```

## Prerrequisitos

1. `E2E_SELLER_PHONE` en `.env` — teléfono de un vendedor registrado en `benfresh.vendedores`.
2. Cliente de prueba con pedidos: `suplai-platform-test` (`5491133333333`) o el `client_identifier` de cada caso.
3. Healthcheck OK: `python scripts/healthcheck_schema.py --schema benfresh`

## Comandos

```bash
# Solo casos reales (secuencial por defecto en manifest)
python scripts/test_agent_e2e.py --schema benfresh --suite real --seller --sequential

# Casos reales + 3 variantes generadas por LLM
python scripts/test_agent_e2e.py --schema benfresh --suite real --seller --sequential --expand 3

# Híbrido: casos reales primero, luego suite genérica de catálogo
python scripts/test_agent_e2e.py --schema benfresh --suite hybrid --seller
```

## Formato `caso.json`

```json
{
  "name": "Nombre legible",
  "sequential_order": 1,
  "message_file": "mensaje.txt",
  "client_identifier": "suplai-platform-test",
  "expected_tools": ["resolve_free_text_order"],
  "expected_tools_any": ["create_order_for_client", "edit_order_for_client"],
  "expected_skus": [],
  "expected_behavior": "Qué debe hacer el agente...",
  "tags": ["lista", "reenvio"]
}
```

- `expected_tools`: todas deben ejecutarse (si el auditor lo valida).
- `expected_tools_any`: al menos una (útil cuando hay varias tools válidas).
- Para fotos: usá `mensaje_simulado.txt` con prefijo `[Consulta con foto por WhatsApp]`.
