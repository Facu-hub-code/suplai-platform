# Skills vendor (skills.sh)

Esta carpeta contiene **symlinks** generados por `scripts/install-vendor-skills.sh`.
No editar manualmente.

| Ubicación | Rol |
|-----------|-----|
| `.agents/skills/` | Copia canónica (gitignored). Cursor + Antigravity. |
| `.cursor/skills/_vendor/` | Symlinks para que Cursor descubra skills vendor sin mezclarlas con las Suplai. |
| `.cursor/skills/*` (resto) | Skills **custom Suplai** — fuente de verdad en git. |

## Setup (cada dev, tras clone)

```bash
cd platform   # raíz suplai-platform
bash scripts/install-vendor-skills.sh
```

Catálogo y mapeo con skills Suplai: `skills-vendor.manifest.json` y sección en `AGENTS.md`.
