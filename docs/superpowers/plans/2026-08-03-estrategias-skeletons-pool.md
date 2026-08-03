# Estrategias skeletons + pool rotativo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`.

**Goal:** Eliminar plantilla seed; biblioteca de ideas por tenant; pool de salida temático con variables 1:1; rotación semanal; notificaciones BO.

**Architecture:** Skeleton ideas → Salida Meta pool → Planner themes + Variable Resolver → Dispatcher → theme_stats + BO notifications.

**Tech Stack:** backend-supabase (asyncpg, Meta Graph), product-management-app (Next.js), platform SPEC-026.

**Repos / ramas:** `feat/estrategias-skeletons-pool` en platform, backend-supabase, product-management-app.

Ver plan Cursor adjunto y SPEC-026 § Fase 7.
