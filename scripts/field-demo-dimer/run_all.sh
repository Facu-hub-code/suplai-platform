#!/usr/bin/env bash
# Ejecuta todas las fases del seed demo dimer en orden (Supabase SQL Editor o psql)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for f in phase0_config phase1_templates phase2_productos_ab phase3_pedidos phase4_torneo_objetivos; do
  echo "== seed_dimer_${f}.sql =="
  cat "${DIR}/seed_dimer_${f}.sql"
  echo ""
done
