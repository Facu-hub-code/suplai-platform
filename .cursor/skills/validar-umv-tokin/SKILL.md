---
name: validar-umv-tokin
description: >-
  Compara la unidad mínima de venta del alta automática contra la conversión
  de Tokin. Usar al implementar o cambiar el mapeo de unidades del spec 127,
  o cuando haya que verificar unidades por display y bulto de un SKU de Almaro.
---

# Validar UMV contra Tokin

Spec: `docs/specs/127-alta-automatica-catalogo-erp.md`.

Tokin publica la conversión (`Display (N Unidades)`, `Bulto (M Displays)` o `Bulto (M unidades)`). GEV aporta la unidad del precio. El nombre aporta el pack que GEV no manda. El script aplica esa regla y dice si es equivalente a Tokin.

No escribe la base. No pisa una UMV ya curada.

## Correr

Desde la raíz de `platform`:

```bash
python .cursor/skills/validar-umv-tokin/scripts/comparar_umv_tokin.py \
  --gev implementacion/almaro/inputs/gev-articulos-20261001.json \
  --codes 14336,7048,13315,3312,14772,14361,14611,4013,12626,1009,5312,10204
```

Hace falta red. Los doce anclas del spec tienen que salir `ok`. `7208` tiene que salir `diff` (el nombre arma bulto 36 y Tokin dice 12).

Para un lote del snapshot, `--gev` sin `--codes` toma las primeras `--limite` filas. `--json-out` guarda el detalle.

## Cómo leer el resultado

| Estado | Qué hacer |
|---|---|
| `ok` | La regla y Tokin describen el mismo pack. |
| `diff` | No cambies la regla para callar un solo SKU. Dejalo en el test como desacuerdo, salvo que el patrón se repita y el spec se actualice. |
| `sin_tokin` | Tokin no tiene el `ARC-10{código}`. No es un fallo de la regla. |
| `sin_unidad` | Sin `UNIDAD_VENTA` no se promueve. |
| `sin_conversion` | El producto está en Tokin y no trae la conversión. No cuenta como `ok`. |

Display 1 en Tokin es la unidad de venta. Si GEV dice que ese display trae K piezas, K no contradice ese 1.

## Al implementar el backend

La función pura del PR tiene que coincidir con `mapear_umv` de `scripts/comparar_umv_tokin.py`. Los tests de CI usan los anclas ya corridos y no pegan a Tokin. Si cambia la regla, se vuelve a correr este script y se actualizan los anclas del spec en el mismo cambio.
