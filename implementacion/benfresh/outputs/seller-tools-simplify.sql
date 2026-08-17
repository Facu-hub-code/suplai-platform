-- Benfresh seller tools simplify — generado 2026-07-16T19:28:43.818429+00:00
-- DRY RUN / revisar antes de aplicar. display_name es global (core.agent_tools).

BEGIN;

-- 1) Editorial global (nombres canvas)
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('check_order_sync_status', 'Estado de sync del pedido', 'vendedor', 'Si el pedido ya sincronizó con el ERP/Field.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('clear_seller_context', 'Limpiar contexto', 'vendedor', 'Borra cliente seleccionado e historial de sesión.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('confirm_order_for_client', 'Confirmar pedido del cliente', 'vendedor', 'Confirma el pedido del cliente vía Field/sistema.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('create_distributor_ticket', 'Crear ticket de soporte', 'vendedor', 'Abre un ticket humano en la distribuidora.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('edit_order_for_client', 'Editar pedido del cliente', 'vendedor', 'Agrega/edita líneas del pedido del cliente.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_field_app_link', 'Link de Suplai Field', 'vendedor', 'Envía el link de la app Field.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_open_order_status_for_client', 'Pedido abierto del cliente', 'vendedor', 'Resume el pedido abierto del cliente seleccionado.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_product_by_code', 'Producto por código', 'vendedor', 'Trae un producto exacto por SKU/código.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_client_details', 'Ver detalle del cliente', 'vendedor', 'Muestra ficha del cliente y lo deja seleccionado.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_client_summary', 'Resumen de cliente (Field)', 'vendedor', 'Resumen Field de un cliente.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_daily_route', 'Ruta del día', 'vendedor', 'Ruta y visitas del día (Field).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_progress', 'Mi progreso', 'vendedor', 'Progreso/puntos Field.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_selected_client', 'Cliente seleccionado', 'vendedor', 'Indica qué cliente está seleccionado ahora.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('get_seller_tasks', 'Mis tareas', 'vendedor', 'Tareas Field del vendedor.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('list_seller_clients', 'Listar mis clientes', 'vendedor', 'Lista la cartera de clientes del vendedor.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('load_seller_order_text', 'Cargar pedido por texto', 'vendedor', 'Interpreta un pedido en texto libre y lo carga al cliente.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('manage_contact_agenda', 'Preferencias de contacto', 'vendedor', 'Guarda preferencias de horario/contacto del chat.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('ping', 'Prueba de conexión', 'vendedor', 'Responde un eco para verificar que el agente está vivo.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('search_products', 'Buscar productos', 'vendedor', 'Busca productos del catálogo por texto (nombre, marca, etc.).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('search_products_by_category', 'Buscar por categoría', 'vendedor', 'Lista productos filtrando por categoría.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_catalog_query', 'Consulta de catálogo', 'vendedor', 'Consulta stock/precio/novedades sin armar pedido (opt-in).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_client_query', 'Consulta de cliente', 'vendedor', 'Consultas sobre un cliente de la cartera (opt-in).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_help', 'Ayuda del vendedor', 'vendedor', 'Manual corto de uso del agente vendedor.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_my_metrics', 'Mis métricas', 'vendedor', 'Métricas del vendedor (opt-in).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_orders_query', 'Consulta de pedidos', 'vendedor', 'Consultas sobre pedidos del vendedor (opt-in).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('seller_promo_pricing_query', 'Consulta de precios y promos', 'vendedor', 'Consulta promos y lista de precios del cliente (opt-in).', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('set_seller_selected_client', 'Elegir cliente', 'vendedor', 'Fija el cliente sobre el que se opera el pedido.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();
INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)
VALUES ('suggest_order_boost_for_client', 'Sugerir productos al pedido', 'vendedor', 'Sugiere ítems para subir el monto del pedido.', 'active', 100)
ON CONFLICT (tool_name) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  short_description = EXCLUDED.short_description,
  updated_at = NOW();

-- 2) Bloqueos runtime solo Benfresh (tools_habilitadas)
UPDATE public.distribuidoras
SET tools_habilitadas = COALESCE(tools_habilitadas, '{}'::jsonb) || '{"check_order_sync_status": false, "get_product_by_code": false, "get_seller_selected_client": false}'::jsonb
WHERE schema_name = 'benfresh';

COMMIT;
