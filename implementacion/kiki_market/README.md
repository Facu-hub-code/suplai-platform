# Kiki Market (`kiki_market`)

Tienda naturista en Villa Carlos Paz. Catálogo desde export Tienda Nube.

- **Schema:** `kiki_market`
- **Owner:** `admin@kikimarket.com` / `Suplai2026`
- **Sitio:** https://kikimarket.com.ar
- **Precio:** lista única = precio Tienda Nube × 0.60
- **Modo:** completo (sin recorte demo)

## Origen

`inputs/tiendanube-catalogo.csv` (copia UTF-8 del export de escritorio).

## Scripts

```bash
python3 implementacion/kiki_market/scripts/generar_fase01.py
python3 implementacion/kiki_market/scripts/provision_tenant.py
# recién después de "confirmar carga":
python3 implementacion/kiki_market/scripts/cargar_fase01.py
```
