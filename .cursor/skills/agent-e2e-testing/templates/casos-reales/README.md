# Plantilla — casos reales E2E

Copiá esta carpeta a `implementacion/{schema}/casos-reales/` y adaptá.

## Archivos incluidos

| Archivo | Propósito |
|---------|-----------|
| `manifest.json` | Perfil, secuencial, env del teléfono vendedor |
| `contexto.md` | Narrativa AS-IS/TO-BE para el LLM (`--expand`) |
| `casos/01-ejemplo/` | Caso mínimo de referencia |

## manifest.json

- `profile`: `seller` | `client`
- `sequential_default`: `true` si los casos encadenan un mismo pedido/sesión
- `sender_phone`: override fijo; si es `null`, usa `E2E_SELLER_PHONE` (seller) o cliente de prueba

## caso.json (campos clave)

- `expected_tools`: todas deben ejecutarse (validación estricta en traza).
- `expected_tools_any`: al menos una (útil si hay varias tools válidas).
- `message_file` / `mensaje.txt`: texto enviado al webhook.
- `mensaje_simulado.txt`: para fotos — prefijo `[Consulta con foto por WhatsApp]`.
- `imagen.*`: referencia visual; no se envía binario en E2E v1.

## Comando

```bash
python scripts/fase-09-e2e/test_agent_e2e.py --schema {schema} --suite real --seller --sequential --expand 2
```

## Ejemplo productivo

Ver `implementacion/benfresh/casos-reales/` (teléfono central, reenvíos de vendedores).
