# Anexo — Character brief "Facundo" + guion humanizado

**Spec principal:** [008-spec-podcast-voz-humana.md](./008-spec-podcast-voz-humana.md)
**Estado:** Diseño (propuesta)
**Fecha:** 2026-06-20

---

## 1) Quién es Facundo

| Atributo | Definición |
|----------|------------|
| Nombre | **Facundo** |
| Rol | Host de **Suplai Spec Cast**: te resume specs en audio. |
| Género / edad | Masculino, joven (~25–35). |
| Acento | **Argentino rioplatense** (Buenos Aires / interior, neutro arg.). |
| Tono | Cercano, claro, con buena onda; informal-profesional. Ni locutor acartonado ni excesivamente canchero. |
| Ritmo | Ágil pero respirado; pausas para que se entienda. |
| Identidad sonora | Voz del propio usuario (clonada) como meta; voz argentina masculina pre-hecha como fallback. |

### Cómo habla (do / don't)

| ✅ Sí | ❌ No |
|-------|-------|
| Voseo: *tenés, mirá, fijate, acordate* | Tuteo: *tienes, mira, fíjate* |
| Frases cortas, una idea por vez | Párrafos largos con subordinadas |
| Muletillas naturales y moderadas | Sobrecarga de *che / posta / viste* |
| Explicar el *por qué*, no leer la tabla | Deletrear SQL, paths o checkboxes |
| Cierre con gancho ("nos vemos en la próxima") | Terminar abrupto sin outro |

---

## 2) Intro y outro fijos

**Intro:**
> "¡Buenas! Soy Facundo y esto es Suplai Spec Cast. Hoy te resumo, en pocos minutos, la spec {número}: {título}. Dale que arrancamos."

**Outro:**
> "Y eso fue todo por hoy. Si querés, te leo otra spec cuando quieras. Soy Facundo, nos vemos en la próxima. ¡Chau!"

---

## 3) Comparativa de proveedores de voz

| Proveedor | Naturalidad | Acento AR | Clona tu voz | SSML / control | Costo aprox. | Cuándo usarlo |
|-----------|-------------|-----------|--------------|----------------|--------------|----------------|
| **macOS `say`** (actual) | Baja | No | No | Limitado | $0 | Fallback offline / sin red |
| **Azure `es-AR-TomasNeural`** | Alta | **Nativo** | No | **Sí (SSML completo)** | Pago por carácter | Nivel 1: argentino ya, sin clonar |
| **OpenAI TTS** (`onyx`/`ash`) | Muy alta | Parcial | No | Limitado | Pago por carácter | Naturalidad rápida, acento no garantizado |
| **ElevenLabs** | Muy alta | Configurable | **Sí** | Parcial (estabilidad/estilo) | Pago por crédito | **Meta: clonar tu voz (Facundo)** |

**Recomendación:** empezar con **Azure `es-AR-TomasNeural`** (argentino nativo, sin fricción) y migrar a **ElevenLabs con voz clonada** del usuario para lograr "mi voz".

---

## 4) Ejemplo: antes robótico → después humano

Tomando un fragmento de la spec 004 (clasificación A/B).

**Antes (TTS actual, lectura plana):**
> "Las distribuidoras B2B manejan una lógica comercial interna sobre sus SKUs que hoy no está reflejada en la plataforma. Cada distribuidora define dos categorías estratégicas con su propio significado. Tipo A, orientado a alta rotación y levantar pedido, mueve volumen. Tipo B, orientado a alta rentabilidad, genera margen al vendedor."

**Después (Facundo, humanizado):**
> "Mirá, esto sale de algo bien concreto: cada distribuidora tiene su cabeza comercial sobre los productos… pero hoy eso no vive en ningún lado del sistema. Así que metemos dos etiquetas. La A es la de volumen —lo que mueve la aguja, lo que levantás sí o sí—. Y la B es la de plata —lo que te deja margen—. Ojo: qué significa cada una la define cada distribuidora, nosotros solo guardamos la letra."

### Qué cambió

- Voseo y tono oral (*mirá, levantás, te deja*).
- Frases partidas con pausas (los guiones largos marcan respiración).
- Metáfora cotidiana (*mueve la aguja*, *la de plata*) en vez de jerga.
- Se mantiene la **precisión** (A=volumen, B=margen, significado por tenant).

---

## 5) Marcas de prosodia (para implementación futura)

Cuando se use un backend con SSML (Azure), el guion puede anotarse:

```xml
<speak>
  <prosody rate="medium">
    Mirá, esto sale de algo bien concreto<break time="300ms"/>
    cada distribuidora tiene su cabeza comercial sobre los productos…
    <break time="400ms"/> pero hoy eso no vive en el sistema.
  </prosody>
</speak>
```

Para backends sin SSML (ElevenLabs), la naturalidad se logra con **puntuación**, **frases cortas** y los parámetros de estabilidad/estilo del modelo.
