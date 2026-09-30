-- Offboarding distribuidora_saffadi → WhatsApp a kiki_market
-- Schema origen: distribuidora_saffadi
-- tenant_id origen: 99e26d8d-81c6-4c10-904d-5d3d942714fb
-- Destino: kiki_market / 7fa7dee6-1aaa-48d1-b60c-46803820f0c1
-- Autorización: ELIMINAR TENANT distribuidora_saffadi
-- No descifra secretos. Ejecutar fases en orden.

-- =============================================================================
-- FASE A — reubicar WhatsApp
-- =============================================================================

UPDATE public.tenant_secrets
SET tenant_id = '7fa7dee6-1aaa-48d1-b60c-46803820f0c1',
    updated_at = now()
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb'
  AND name LIKE 'whatsapp.%';

UPDATE public.distribuidoras
SET agent_phone_number = NULL,
    updated_at = now()
WHERE schema_name = 'distribuidora_saffadi'
  AND id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

UPDATE public.distribuidoras
SET agent_phone_number = 5493582430647,
    updated_at = now()
WHERE schema_name = 'kiki_market'
  AND id = '7fa7dee6-1aaa-48d1-b60c-46803820f0c1';

UPDATE public.meta_plantillas
SET tenant_id = '7fa7dee6-1aaa-48d1-b60c-46803820f0c1'
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

-- =============================================================================
-- FASE B — borrar datos de distribuidora_saffadi
-- =============================================================================

DELETE FROM core.conversation_events
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.followup_sequence_executions
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.agent_turns
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.seller_context
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.inbound_messages
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.message_buffers
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.agent_tool_executions
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.agent_tool_runs
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.agent_rag_candidates
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.conversation_ad_attribution
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.tienda_link_events
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM core.location_tokens
WHERE schema_name = 'distribuidora_saffadi';

DELETE FROM core.conversations
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb'
   OR schema_name = 'distribuidora_saffadi';

DELETE FROM public.followup_sequences
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.tenant_cross_sell_mappings
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.tenant_up_sell_mappings
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.notification_event_config
WHERE tenant_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.sales_engine_retrain_logs
WHERE schema_name = 'distribuidora_saffadi';

DELETE FROM public.implementation_project_milestone_log
WHERE project_id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6';

DELETE FROM public.implementation_project_updates
WHERE project_id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6';

DELETE FROM public.implementation_project_files
WHERE project_id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6';

DELETE FROM public.implementation_project_user_stories
WHERE project_id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6';

DELETE FROM public.customer_success_events
WHERE project_id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6';

DELETE FROM public.implementation_projects
WHERE id = 'bc21723e-d43c-464f-a6c6-01d17d1084e6'
  AND distribuidora_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.onboarding_catalog_jobs
WHERE distribuidora_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM public.profiles
WHERE distribuidora_id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DROP SCHEMA IF EXISTS distribuidora_saffadi CASCADE;

DELETE FROM public.distribuidoras
WHERE schema_name = 'distribuidora_saffadi'
  AND id = '99e26d8d-81c6-4c10-904d-5d3d942714fb';

DELETE FROM auth.users
WHERE id IN (
  '12cc3c7f-2b5d-4d9f-bd42-296098b6ec8b',
  '5dcb710c-4139-4445-bc11-90a8e2cd66bf',
  '3212ff8f-8ca7-4f03-ad67-8bdc6a3dfa0f'
)
AND email IN (
  'mariano@saffadi.com',
  'alejandro.saffadi@suplaisales.com',
  'faculoren7@saffadi.com'
);
