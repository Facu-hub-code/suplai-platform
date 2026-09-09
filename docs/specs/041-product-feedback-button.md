# 041 — Botón de feedback (backoffice → Brevo)

**Estado:** En implementación  
**Fecha:** 2026-09-09  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform` (este doc)  
**Ramas sugeridas:** `feat/product-feedback-button`  
**Destinatario:** `facundo@suplaisales.com` (env `PRODUCT_FEEDBACK_TO_EMAIL`)

---

## Objetivo

Que un operador del backoffice tenant mande feedback de producto (texto + imágenes/videos) sin salir del header. El texto se puede reescribir con IA; el mail llega por Brevo; los adjuntos viven 30 días en Supabase Storage.

---

## Criterios de aceptación

- Botón de feedback a la **izquierda** de la campana de Notificaciones (header tenant).
- Modal con textarea obligatorio, **Enriquecer con AI** (reemplaza el texto; **Deshacer** vuelve al original) y dropzone + file picker.
- Hasta **5** archivos: imagen ≤ 10 MB (`jpeg/png/webp/gif`), video ≤ 50 MB (`mp4/webm/quicktime`).
- Enviar manda mail HTML a Facundo vía Brevo, con Reply-To del operador. El cuerpo incluye tenant, usuario, rol, sección y texto; si se enriqueció, también el original.
- Adjuntos **no** van como attachment de Brevo: links `GET /product-feedback/media/{token}` válidos 30 días.
- Tras 30 días el job de cleanup borra objects + filas. El texto del mail permanece en la bandeja.
- Si OpenAI falla, toast y se puede enviar el texto original. Si Brevo falla, toast de error y no se da por enviado.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Superficie | Solo backoffice tenant | El pedido es “al lado de Notificaciones”; ese header no existe en `/admin` ni Field | Widget en Field / admin / tienda |
| Entrega | Brevo transaccional + links | Ya hay `brevo_send.py` y sender verificado; Facundo lo ve en Gmail | Slack, inbox CS, Intercom/Canny |
| Videos | Storage privado + token de descarga | Brevo ~20 MB; un video de 50 MB no entra en el mail | Adjuntar binario al SMTP |
| IA | Reescritura revisable (`gpt-4o-mini`) | El operador confirma el texto; no se inventa contexto | Auto-adjuntar URL/tenant dentro del rewrite; enviar sin revisar |
| Metadata | Email/schema/sección en el **mail**, no en el rewrite | Trazabilidad operativa sin mezclarla con la voz del usuario | Que la IA “enriquezca” con datos de sesión |
| Upload | Signed URL cliente → Storage | No pasa el video por Railway; mismo patrón que proyectos de implementación | Multipart al backend |
| Links del mail | Token opaco + redirect backend | Un signed URL de Storage expira en horas; el token vive 30 días | Bucket público; signed URL de 30d (límite de Supabase) |
| Persistencia | Tablas `public` + TTL | Hace falta saber qué borrar a los 30 días; no es un inbox de producto | Solo Storage sin índice; eventos de Customer Success |
| Cleanup | APScheduler 04:00 ART | Ya hay jobs diarios en `main.py`; no depende de lifecycle de plan Pro | Solo lifecycle nativo de Storage |

---

## Alcance explícito

### Incluido (v1)

- Botón + modal en el header tenant.
- `POST /{schema}/product-feedback/enrich`
- `POST /{schema}/product-feedback/attachments/signed-upload-url`
- `POST /{schema}/product-feedback`
- `GET /product-feedback/media/{token}` (sin login)
- Bucket `product-feedback` + tablas + job de purge a 30 días.
- i18n es / pt / en del copy del modal.

### Fuera de alcance (v1)

- `/admin`, Field, tienda.
- Historial de feedback en Customer Success o Notificaciones (`ia_tickets`).
- Pegar desde clipboard, grabar pantalla, o capturar la vista actual.
- Feature flag. Enrich es best-effort (sin `OPENAI_API_KEY` el botón falla con toast; enviar sigue).

---

## Orden de implementación

| Orden | Repo | Rama | Dependencia |
|-------|------|------|-------------|
| 1 | `suplai-platform` | `feat/product-feedback-button` | Este spec |
| 2 | `backend-supabase` | `feat/product-feedback-button` | Migración 119 → service → router → job → tests |
| 3 | `product-management-app` | `feat/product-feedback-button` | API usable; botón + proxies + i18n |

**Merge humano:** backend (migración aplicada en Suplai-east) → backoffice → spec platform.

---

## Migración de base de datos

**Archivo:** `backend-supabase/sql/119_product_feedback.sql`

- Bucket privado `product-feedback` (50 MB, MIME imagen/video).
- `public.product_feedback`: schema, usuario, sección, texto original/enviado, `created_at`, `expires_at` (now + 30 días).
- `public.product_feedback_attachments`: path, mime, size, `download_token`.
- Sin seed / backfill.
- Rollback: `DROP TABLE ... CASCADE` + borrar bucket (adjuntos se pierden; los mails ya enviados quedan).
- Riesgo bajo: tablas nuevas, sin ALTER de tablas de negocio.

---

## Plan de prueba en CI/CD

- Backend: `pytest tests/test_product_feedback.py` (validación MIME/tamaño, enrich mock OpenAI, submit mock Brevo, token inválido/expirado, cleanup).
- Checks existentes de backend y backoffice deben quedar verdes en lo nuevo.
- Smoke de migración: apply 119 en el proyecto `cvlbietibaaehgeimxgw` antes del merge.
- Backoffice: no hay suite unitaria (gap previo); lint/build del PR.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000` + backoffice `3000` (Maps). Tenant de prueba (p. ej. `demo`). Usuario logueado.

1. Ver el botón a la izquierda de la campana de Notificaciones.
2. Abrir el modal, escribir un texto corto, enviar. Verificar mail en `facundo@suplaisales.com` (tenant, usuario, sección, texto).
3. Abrir de nuevo, **Enriquecer con AI**, revisar el rewrite, **Deshacer**, volver a enriquecer, enviar. El mail debe traer original + enviado.
4. Arrastrar 1 imagen y 1 video dentro de límites; preview; quitar uno; enviar. Abrir el link del adjunto desde el mail.
5. Rechazo: 6º archivo, video > 50 MB, o tipo no permitido — mensaje de error, no se manda.
6. (Opcional) cortar `OPENAI_API_KEY` / `BREVO_API_KEY` y confirmar toasts sin bloquear el resto del BO.
