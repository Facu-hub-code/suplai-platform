# Grok Bot — reglas y skills Suplai (Supabase)

Pack para el Grok Bot que ya tiene el MCP de Supabase. Sirve para preguntas operativas del estilo: *¿ayer salieron los envíos del carrusel de Gonzales?*

## Qué cargar

| Pieza | Dónde | Archivo |
|-------|--------|---------|
| Regla corta (siempre en contexto) | Cursor Dashboard → Team Rules → scope **Grok Bot** | [TEAM-RULE.md](TEAM-RULE.md) |
| Skill MCP | Grok Bot → guardar skill / Plugins → Yours → enable | `.grok/skills/suplai-supabase-mcp/SKILL.md` |
| Skill envíos HSM | igual | `.grok/skills/check-hsm-sends/` (`SKILL.md` + `reference.md`) |

Si el Bot tiene el repo en su computadora cloud, Grok descubre skills en `.grok/skills/` al trabajar en este directorio.

## Cómo instalar en el Bot (sin clonar)

1. Pegá el contenido de `TEAM-RULE.md` como team rule (Grok Bot).
2. En el chat del Bot:

> Guardá esto como skill `suplai-supabase-mcp`. Incluí el SKILL.md que te pego.

3. Repetí con `check-hsm-sends` y, en un segundo mensaje, el `reference.md` para que lo deje junto a la skill.
4. Settings → Plugins → Yours: enable ambas skills en ese Bot.
5. En el composer, `/check-hsm-sends` debería aparecer.

## Prompt de prueba

```
¿Ayer salieron bien los envíos del tenant gonzales con la plantilla de Meta con carrusel?
```

Un Bot bien configurado debería: resolver `gonzales` → `tenant_id`, filtrar ayer en ART, mirar `envios_plantillas` + agendas (`gg_carousel_promos_arcor_v*`) y dar veredicto OK / parcial / falló con conteos.

Variantes:

```
Hoy a las 15, ¿salió la agenda puntual del carrusel de Gonzales?
```

```
Compará envíos del carrusel de Gonzales entre ayer y anteayer.
```

## MCP

URL típica (read-only):

`https://mcp.supabase.com/mcp?project_ref=cvlbietibaaehgeimxgw&read_only=true`

Cada tool call necesita `project_id: cvlbietibaaehgeimxgw`.
