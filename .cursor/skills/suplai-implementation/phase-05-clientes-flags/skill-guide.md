# Guía de Uso — Fase 5: Flags de Clientes (suplai-implementation-phase-05)

Esta guía detalla los pasos para actualizar y enriquecer a los 50 clientes mock de la base de datos asignándoles estados de validación de WhatsApp e identificadores del ERP (o marcándolos como prospectos).

> [!NOTE]
> **Ejecución por script (obligatoria)**
> La Fase 5 ya no se resuelve con SQL manual. Primero se genera el CSV local con `preparar_clientes_flags.py` y luego se carga con `cargar_clientes_flags.py`. El agente puede revisar los datos, pero la escritura a BD debe pasar por esos scripts para mantener la distribución y la trazabilidad consistentes.

---

## 📋 Requisitos Previos

1. **Fase 4 completada**: Los 50 clientes mock deben estar insertados.
2. **Chequeo de Columnas**: Verificar si el esquema de base de datos tiene campos como `whatsapp_estado`, `whatsapp_validado_at`, o `codigo` (ERP).

---

## 🚀 Paso a Paso de la Ejecución

### 1. Preparar el CSV
Tomar el archivo de Fase 4 (`implementacion/{schema}/outputs/phase-04-clientes.csv`) y correr:

```bash
python scripts/fase-05-clientes-flags/preparar_clientes_flags.py --esquema <schema>
```

El script:
- Genera `implementacion/{schema}/outputs/phase-05-clientes-flags.csv`.
- Asigna 40 clientes ERP y 10 prospectos.
- Usa `codigo_erp` secuencial desde `25001`.
- Marca `whatsapp_estado` y `whatsapp_validado_at` según la distribución fija.
- Escribe las columnas `phone_number`, `razon_social`, `codigo_erp`, `whatsapp_estado`, `whatsapp_validado_at`, `etiqueta` e `is_prospect`.

### 2. Cargar al tenant
Una vez revisado el CSV, ejecutar:

```bash
python scripts/fase-05-clientes-flags/cargar_clientes_flags.py --esquema <schema>
```

El script:
- Hace `UPDATE` sobre `{schema}.clients` por `phone_number`.
- No inserta filas nuevas.
- Valida la distribución final y reporta los contadores en consola.

### 3. Verificación
La verificación principal ya queda impresa por el script de carga. Si hace falta revisar a mano:

```sql
SELECT COUNT(*) FROM {schema}.clients WHERE codigo > 0; -- Debe ser aproximadamente 40
SELECT COUNT(*) FROM {schema}.clients WHERE codigo = 0; -- Debe ser aproximadamente 10
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["05"].estado = "cargado"` y registrando `cargado_at`.
2. Proceder a la Fase 6.
