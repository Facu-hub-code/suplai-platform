# Handoff — sondeo del ERP Sistel desde Argentina

**Para:** dev con salida a internet en Argentina
**Tenant:** `rawson` · **Proveedor ERP:** Sistel
**Objetivo:** correr un script de solo lectura contra la API del ERP y devolver dos archivos JSON.

No hay que escribir código ni tocar ninguna base de datos. El script solo lee.

## Por qué te lo pasamos a vos

El servidor del ERP (`asp12.selfip.net:3448`, IP real `186.123.180.126`) responde ping desde cualquier lado, pero **descarta todo el tráfico TCP** que llega desde nuestra IP en España — probamos los puertos 80, 443, 3448 y 8080, los cuatro dan timeout sin un `connection refused`. Eso es un firewall con lista blanca de IP de origen, y la hipótesis es que solo aceptan IPs argentinas. Desde tu conexión debería entrar.

Ojo con un detalle: el host usa DNS dinámico (`selfip.net`, TTL 60) y algunos resolvers de ISP devuelven `208.91.112.55`, que es una IP de parking y no el servidor. El script ya resuelve por DNS-over-HTTPS y pega contra la IP real con cabecera `Host`, así que no te tenés que preocupar por eso.

## Qué correr

Necesitás Python 3 (sin dependencias externas) y el repo `suplai-platform`.

```bash
cd suplai-platform
cp implementacion/rawson/.env.example implementacion/rawson/.env
```

Editá `implementacion/rawson/.env` y completá `SISTEL_PASS` con la contraseña que te pasamos **por canal seguro, nunca por el repo**. El resto de los valores ya vienen cargados.

```bash
python3 implementacion/rawson/scripts/probe_sistel.py
```

## Cómo se ve que funcionó

```
[dns] asp12.selfip.net → local=…  doh=186.123.180.126
[tcp] 186.123.180.126:3448 abierto
[login] OK — claves de respuesta: [...]
[vistas] HTTP 200
[vistas] N alias: [...]
[raw_productos] OK modo=simple filas=5 cols=23
```

Lo que nos tenés que devolver son los dos archivos que deja en `implementacion/rawson/outputs/`:

- `erp-sistel-vistas.json` — catálogo de alias del ERP
- `erp-sistel-probe.json` — por cada alias: modo, columnas, 3 filas de muestra y paginación

Mandalos por el canal que acordemos. **No los commitees**: pueden traer datos de clientes reales.

## Si falla

| Qué ves | Qué significa | Qué reportar |
|---|---|---|
| `[tcp] … sin conexión` | Tu IP tampoco está habilitada | Tu IP pública (`curl https://api.ipify.org`) para pedir la whitelist |
| `[login] HTTP 401` | Credenciales rechazadas | El cuerpo del error tal cual |
| `[login] HTTP 0` con timeout | El puerto filtra igual | Lo mismo que la primera fila |
| `[vistas] HTTP 400` | La API está en modo flexible | La salida completa, la ajustamos nosotros |
| Algún alias da `HTTP 400` | Esa vista exige filtros o `id` | Cuáles fallaron y con qué mensaje |

Si el login entra pero un alias devuelve `[]`, no es necesariamente un error: en este contrato la lista vacía puede ser simplemente "sin resultados".

## Si tenés contacto con Sistel

Estas cuatro preguntas nos destraban el mapeo y no dependen de la conexión:

1. ¿La API corre en **modo simple** o **flexible**? Cambia qué filtros y rutas aceptan.
2. Tabla completa de alias `raw_*` → qué significa cada uno. Solo conocemos `raw_productos`; necesitamos clientes, vendedores, precios, listas y stock.
3. ¿Cuál es el `limit` máximo por página?
4. ¿Cuánto dura el `access_token` y está habilitado `POST /auth/refresh`?

## Contexto técnico

- Manual de la API y plan completo: [`erp-rawson-api-sistel.md`](erp-rawson-api-sistel.md)
- Script: [`../scripts/probe_sistel.py`](../scripts/probe_sistel.py)
