# Guía de Uso — Fase 1.3: Personalización del Prompt del Agente (suplai-implementation-phase-01-3)

Esta guía detalla el proceso para estructurar y personalizar la identidad (`identidad`), el contexto operativo (`contexto`) y las políticas comerciales (`reglas_negocio`) del agente de IA de WhatsApp de un distribuidor mediante inferencia de LLM.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Si eres un agente de IA leyendo esta guía, puedes realizar la estructuración y la redacción del prompt de manera autónoma utilizando un modelo LLM con temperatura baja (ej: `gpt-4o-mini`).
>
> **MANDATORIO**: Antes de impactar los cambios en Supabase, **debes presentar los textos de identidad y contexto propuestos al usuario** para que los valide o solicite ajustes rápidos.

---

## 📋 Requisitos Previos

1. **Catálogo cargado**: La Fase 1 debe estar completada y con estado `cargado` en `manifest.yaml` para conocer el rubro y la marca líder.
2. **Acceso MCP**: Conexión a la base de datos Supabase configurada en modo escritura.

---

## 🚀 Paso a Paso de la Ejecución

El proceso consiste en recopilar las especificaciones humanas del distribuidor, refinarlas con LLM, generar el archivo de configuración y actualizar la tabla maestra `public.distribuidoras`.

### Paso 1: Recopilación de Datos del Distribuidor

El implementador humano o el manifest debe proveer:
- **Rubro**: Tipo de productos que vende (ej: "Golosinas y consumo masivo", "Ferretería industrial").
- **Restricciones / Reglas Especiales**:
  - Restricción de marcas (ej: "Solo vende productos de la marca Arcor").
  - Horarios de atención al público (ej: "Lunes a viernes de 8:00 a 17:00 hs").
  - Mínimos de compra o políticas de envío (ej: "Envío gratis superando los $30.000, si no se retira por depósito").

---

### Paso 2: Generación Estructurada vía LLM

Con base en la información del paso 1, pedir al LLM (usando un prompt del sistema adaptado) estructurar las siguientes tres variables críticas:

#### 1. Identidad (`identidad`)
Define el rol, nombre ficticio de asistente (si tiene), tono y actitud al chatear por WhatsApp (ej. cordial, directo, vendedor enfocado en consumo masivo).
*Ejemplo:*
> "Sos Facu, el asistente virtual de ventas de Colormix. Tu tono es profesional, ágil y servicial. Ayudás a clientes comerciantes y pintores a armar sus pedidos, cotizar presupuestos y evacuar dudas sobre pinturas, rodillos y herramientas de ferretería. Hablás en español rioplatense (voseo suave)."

#### 2. Contexto (`contexto`)
Define los límites operativos de lo que el agente sabe y no sabe, los horarios de atención y las reglas geográficas o de envíos.
*Ejemplo:*
> "Operás en la zona de Rosario y alrededores. El horario de atención comercial es de lunes a viernes de 8:00 a 17:00. No coordinás entregas los fines de semana. Las consultas fuera de horario se responden con una aclaración de que el pedido se procesará al día siguiente hábil. Solo manejás precios en pesos argentinos."

#### 3. Reglas de Negocio (`reglas_negocio`)
Objeto JSON que codifica las políticas estrictas que el agente debe verificar o mencionar (como restricciones de marca, importes mínimos o métodos de pago).
*Ejemplo:*
```json
{
  "solo_marcas": [],
  "monto_minimo_envio": 30000,
  "horario_entrega": "24-48 horas",
  "metodos_pago": ["efectivo", "transferencia bancaria"]
}
```

#### 4. Número de WhatsApp del Agente (`agent_phone_number`)
Generar de manera aleatoria un número de WhatsApp simulado (debe ser un string de dígitos numéricos, ej: `549` + código de área de la ciudad base + 7 dígitos aleatorios).

---

### Paso 3: Guardar Entregable

Escribir el resultado final de la propuesta en:
**`implementacion/{schema}/outputs/phase-01-3-prompt-config.json`**

Este archivo JSON debe almacenar las claves `identidad`, `contexto`, `reglas_negocio` y `agent_phone_number`.

---

### Paso 4: Carga a la Base de Datos (MANDATORIO — Usar Script)

Para impactar los cambios de forma segura en la tabla maestra `public.distribuidoras` de Supabase, se **debe ejecutar obligatoriamente** el script de carga provisto en la base de código:

```bash
python scripts/fase-01-catalogo/aplicar_prompt.py --esquema <nombre_esquema>
```

Este script automatizado se encargará de establecer la conexión, validar la existencia del esquema, estructurar las reglas de negocio en formato JSONB y realizar el `UPDATE` correspondiente.

---

## 🔍 Verificación Post-Carga

El agente debe ejecutar una consulta para verificar que los datos fueron actualizados correctamente en la base de datos:
```sql
SELECT schema_name, identidad, contexto, reglas_negocio, agent_phone_number 
FROM public.distribuidoras 
WHERE schema_name = '{schema}';
```

---

## 🏁 Cierre de la Fase

1. Modificar el archivo `implementacion/{schema}/manifest.yaml`:
   - Cambiar `fases["01.3"].estado` a `cargado`.
   - Registrar `fases["01.3"].cargado_at` al timestamp actual.
2. Invitar al implementador a continuar con la **Fase 2 (Promociones)**.
