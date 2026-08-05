# Futuro — motor de reglas de campañas Meta (stub)

**Estado:** no implementar en v1 del módulo Marketing.

## Intención

Cada X tiempo, mutar parámetros de campañas activas (budget, bid, creative rotation, pausa/reactivación) según señales de conversión (CTWA → conversación → pedido), con la misma lógica conceptual que el motor de re-targeting de estrategias.

## Entradas previstas

- Insights Meta (spend, conversations, CPC)
- Atribución propia (`ctwa_clid` → pedidos)
- Performance por zona / promo del creative package
- Umbrales configurables por tenant

## Salidas previstas

- PATCH a ad sets / ads vía Marketing API
- Eventos de auditoría en tabla futura (`marketing_rule_runs` o similar)
- Alertas en dashboard

Hasta que este módulo exista, el módulo Marketing es **CRUD + publish + lectura Insights**.
