# 141 — Equipo de agentes: reportes

**Estado:** Borrador.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase` (`services/agentes_reportes/`, `core/supabase_storage.py`), `product-management-app` (vista en `/agentes/reportes`).
**Rama sugerida:** `feat/agentes-reportes`.
**Relaciona:** [135](./135-backoffice-agentico.md) (pantalla Reportes), [136](./136-agentes-modelo-de-datos.md) (`core.agentes_reportes`, `core.agentes_avisos`), [139](./139-agentes-tools-mcp.md) (`publicar_reporte`), [125](./125-notificaciones-cola-canales.md) (correo).

---

## Objetivo

Que el resultado de un trabajo llegue como una página web y un PDF guardados en un bucket privado de Suplai, con un correo de aviso al humano y un anexo que cuenta cómo se llegó al resultado.

### Criterios de aceptación

- `publicar_reporte` genera la página HTML y el PDF del mismo contenido, los guarda en el bucket y crea el Reporte.
- El bucket es privado. Todo acceso es por link firmado de corta duración, generado al momento.
- El correo de `reporte.listo` llega al humano asignado con el resumen y un link a `/agentes/reportes/{id}`, no un link firmado.
- El reporte tiene un anexo de traza: pasos clave, preguntas hechas y el contexto que aportó el humano.
- Un reporte no lleva teléfonos ni emails de clientes.
- Si el PDF falla, la página web se publica igual, el reporte queda con `pdf_path` nulo y la traza registra el error.

---

## Bucket

| Decisión | Elección | Por qué |
|----------|----------|---------|
| Storage | Reportes en Supabase Storage, bucket privado `agentes` (`core/supabase_storage.py`). Los datos crudos de `exportar_lote` y `guardar_archivo` van al bucket de GCP `suplai-agentes-datos` ([138](./138-agentes-adaptador-runtime.md)) | El reporte lo arma y lo sirve el backend de Railway; los datos crudos los baja el contenedor en GCP. Cuando el backend migre a GCP, los reportes se mudan al mismo proyecto |
| Path | `{schema}/{trabajo_id}/datos/…`, `{schema}/{trabajo_id}/reporte/v{n}/index.html` y `reporte.pdf` | El prefijo del tenant permite chequear el aislamiento por path |
| Link firmado | 1 hora para ver; 2 horas para los archivos de `exportar_lote` | Corto: el link se puede reenviar. La pantalla pide uno nuevo cada vez |
| Retención | Datos intermedios 180 días; reportes sin vencimiento en el MVP | Los datos crudos pesan y no hacen falta para leer el reporte |

`GET /{schema}/agentes/datos/firmar?path=` rechaza todo path que no empiece con `{schema}/`.

---

## Contenido del reporte

`publicar_reporte` recibe bloques; el backend arma la página. El bot no escribe HTML.

| Bloque | Campos |
|--------|--------|
| `texto` | `titulo`, `markdown` |
| `tabla` | `titulo`, `columnas`, `filas` (hasta 50) o `datos_path` (se toman las primeras 50 filas) |
| `grafico` | `titulo`, `tipo` (`linea`, `barras`), `serie_x`, `series`, `datos_path` |
| `hallazgo` | `titulo`, `cifra`, `explicacion`, `confianza`, `a_confirmar` (bool) |

Estructura fija para el análisis de ventas (prueba 1): resumen ejecutivo, tendencia del período, clientes que crecen, clientes que caen, productos, zonas, preguntas abiertas y anexo. Para el de conversaciones (prueba 2): resumen, rechazos por motivo, productos no encontrados, oportunidades perdidas, ejemplos y anexo.

### Anexo de traza

Lo arma el backend desde `core.agentes_traza`, no el bot: plan, cantidad de pasos por bot, duración, archivos usados, preguntas con su respuesta y contexto aportado por el humano («Faka aclaró que el Súper Norte cerró en julio»). Así el anexo no depende de que el bot recuerde lo que hizo.

---

## Generación

| Formato | Cómo |
|---------|------|
| HTML | Plantilla Jinja2 propia (dependencia nueva en `requirements.txt`), estilos inline, gráficos como SVG generado en el servidor. Sin JavaScript ni recursos externos: se abre igual desde el bucket y dentro del iframe del backoffice |
| PDF | `fpdf2` (ya está en `requirements.txt`, lo usa el PDF de pedidos) a partir de los mismos bloques. Los gráficos se dibujan con las primitivas de `fpdf2` |

Se descarta HTML→PDF con un navegador headless: suma una dependencia pesada al proceso del backend.

Republicar un reporte (el jefe de cuenta corrige tras un contexto nuevo) crea `v{n+1}` y deja la anterior.

---

## Correo de aviso

Al procesar `reporte.listo`, `services/agentes_avisos.py`:

1. Crea el Aviso (`origen_tipo=reporte`, banda según preferencias; default inmediato).
2. Encola un `notification_job` de canal email con plantilla Brevo `agentes_reporte_listo`: asunto «Tu análisis está listo: {titulo}», resumen, tres hallazgos principales y el botón «Ver reporte» → `https://<backoffice>/agentes/reportes/{id}?src=email`.
3. El PDF no va adjunto: el correo es liviano y el acceso queda auditado por login.

La misma vía manda los avisos de pregunta, propuesta y error, con su plantilla.

## Plan de prueba

- Unit: bloques → HTML y PDF; un bloque inválido falla con `campo_invalido` antes de subir nada.
- Aislamiento: firmar `otro_tenant/...` desde `cordoba_frost` → 403.
- PDF roto: se publica la web y la traza muestra el error.
- Correo: llega un solo correo aunque `reporte.listo` se entregue dos veces.
