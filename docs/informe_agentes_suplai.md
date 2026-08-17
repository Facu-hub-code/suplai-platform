# Informe Técnico: Agentes del Ecosistema Suplai Sales

Este documento proporciona una descripción detallada de todos los agentes y motores inteligentes que conforman la plataforma de **Suplai Sales**, sus tecnologías asociadas, responsabilidades, canales de comunicación, arquitectura y cómo interactúan entre sí.

---

## Mapa de Agentes en la Arquitectura

```mermaid
flowchart TB
  subgraph Usuarios [Canales de Usuario]
    PDV[Puntos de Venta (Clientes B2B)]
    VEND_WA[Vendedores en WhatsApp]
    OP_BO[Operadores de Back Office / Supervisores]
    VEND_COMM[Fuerza de Venta en la Calle]
  end

  subgraph Agentes [Agentes y Motores Inteligentes]
    AG_WA[Agente Conversacional WhatsApp\n'agent/']
    COPILOT[Suplai Copilot\n'backend/ + backoffice/']
    ML_ENG[Sales Engine - Motor ML\n'sales-engine/']
    SNIFFER[Sniffer de Conversaciones\n'sniffer/']
  end

  subgraph Datos [Bases de Datos]
    SUPABASE[(Supabase principal\ncore + public + tenants)]
    SNIFFDB[(Postgres Espejo\nKommo CRM)]
  end

  %% Interacciones de Usuarios a Agentes
  PDV -->|Mensajes WhatsApp| AG_WA
  VEND_WA -->|Mensajes WhatsApp| AG_WA
  OP_BO -->|Consultas Lenguaje Natural| COPILOT
  VEND_COMM -->|Chats de venta en Kommo| SNIFFER

  %% Interacciones de Agentes a Datos y entre sí
  AG_WA -->|Lectura/Escritura| SUPABASE
  AG_WA -.->|Links de catálogo| COPILOT
  COPILOT -->|Lectura/Escritura auditada| SUPABASE
  ML_ENG -->|Entrena/Recomienda combos| SUPABASE
  SNIFFER -->|Escribe mensajes/auditoría| SNIFFDB
  COPILOT -.->|Recomendaciones opcionales| ML_ENG
```

---

## 1. Agente Conversacional WhatsApp B2B (`agent/`)

El **Agente Conversacional WhatsApp** es el bot automatizado que interactúa directamente con los clientes minoristas y los vendedores a través de WhatsApp.

* **Propósito:** Automatizar la recepción de pedidos, responder consultas de catálogo, precio e inventario, y gestionar la interacción inicial con los puntos de venta (PdV).
* **Stack Tecnológico:** Python, FastAPI, LangGraph.
* **Canal:** WhatsApp (vía API oficial de Meta Cloud / WhatsApp Business Platform).
* **Esquema de Base de Datos:** Acceso directo a la base de datos principal de Supabase. Aísla la información por tenant a través del número de teléfono del agente (`agent_phone_number`), mapeándolo con la distribuidora correspondiente (`public.distribuidoras.schema_name`).
* **Principales Funciones:**
  * **Captura de Pedidos:** Recibe intenciones de compra en lenguaje natural, valida los productos en la base de datos del tenant, y arma el carrito del cliente.
  * **Derivación a Catálogo Web:** En caso de que el cliente prefiera autogestionarse, el agente genera y envía un link dinámico temporal al catálogo en línea (`tienda.suplaisales.com/{schema}?wp={telefono}`).
  * **Flujo de Trabajo:** Basado en una arquitectura de grafos de agentes con LangGraph (`llm → tools → llm`), donde cada nodo del grafo representa un estado conversacional o la ejecución de una herramienta específica en la base de datos del tenant.

---

## 2. Suplai Copilot (`backend-supabase` / `product-management-app`)

El **Suplai Copilot** es el asistente virtual y de inteligencia comercial integrado directamente en el Back Office de la distribuidora.

* **Propósito:** Permitir a operadores comerciales, supervisores y gerentes consultar métricas, analizar el territorio y ejecutar tareas programadas de marketing mediante lenguaje natural, eliminando la necesidad de generar reportes manuales.
* **Stack Tecnológico:** Backend en FastAPI/Python (para orquestación de LLM, tools y generación de reportes), Frontend en Next.js (React 19, Tailwind CSS).
* **Canal:** Panel lateral deslizable ("Canvas") situado en el lado derecho de la interfaz del Back Office web.
* **Esquema de Base de Datos:** Consume endpoints a través del backend (`/copilot/chat`) que lee y escribe de manera segura en Supabase (`core` para persistencia de conversaciones/logs y el esquema del `{tenant}` para analítica).
* **Principales Funciones:**
  * **Analítica Conversacional (Lectura):** Responde preguntas sobre el producto más vendido, el pedido de mayor facturación del mes, la evolución de ventas en series de tiempo y comparativas de periodos (este mes vs. el anterior).
  * **Visualización de Datos (Artefactos):** Las respuestas no son solo texto; se renderizan componentes interactivos validados mediante esquemas (Zod) como filas de KPI, tablas, gráficos de barras/líneas y mapas de clientes geolocalizados.
  * **Generación de Reportes PDF/Email:** Genera informes consolidados de los análisis del chat en PDF para descarga local o envío automático al email del operador logueado utilizando Brevo.
  * **Escritura Auditada (Crear Agenda):** Permite programar envíos masivos de plantillas de WhatsApp a clientes o grupos específicos en días y horarios concretos. Cuenta con un flujo de seguridad obligatorio de dos pasos: `Dry Run con Preview` -> `Confirmar / Cancelar` mediante un token de un solo uso de 10 minutos. Cada acción guarda un registro de auditoría con la identidad (`user_id`, `email`) del operador.

---

## 3. Motor de Recomendación - Sales Engine (`sales-engine/`)

El **Sales Engine** es el agente analítico y de recomendación que utiliza Machine Learning para optimizar el ticket promedio de compra en el canal mayorista.

* **Propósito:** Predecir y recomendar "combos" de productos personalizados que tienen alta probabilidad de ser comprados juntos en base al comportamiento histórico de pedidos.
* **Stack Tecnológico:** Python, FastAPI, scikit-learn, Docker.
* **Canal:** API REST interna orientada a servicios.
* **Esquema de Base de Datos:** Consulta las tablas del tenant (`{tenant}.pedidos` e `items_pedido`) de Supabase para su entrenamiento y predicción.
* **Principales Funciones:**
  * **Entrenamiento Offline:** Entrena modelos de asociación basados en co-ocurrencia y compras históricas para cada tenant de manera aislada. Los modelos entrenados se guardan de forma persistente en archivos binarios `{schema_name}.pkl`.
  * **Recomendaciones en Caliente (Predict-Combo):** Ofrece un endpoint REST rápido (`POST /v1/tenants/{schema}/predict-combo`) para sugerir combos de productos agregados al carrito, con un peso prioritario a los pedidos realizados en los últimos 90 días para adaptarse a la estacionalidad comercial.
  * **Orquestación de Retraining:** Endpoint expuesto para reentrenar de manera automatizada el modelo del tenant cuando se detectan variaciones de catálogo o de comportamiento de compra.

---

## 4. Sniffer de Vendedores (`sniffer/`)

El **Sniffer** es el agente supervisor que monitorea la actividad y conversaciones que la fuerza de venta de calle mantiene con los puntos de venta externos.

* **Propósito:** Ingerir, auditar y analizar las conversaciones de los vendedores para evaluar tiempos de respuesta, detectar patrones de cierre exitoso y mejorar el pitch comercial.
* **Stack Tecnológico:** Python, FastAPI, Postgres (espejo dedicado), Alembic.
* **Canal:** Webhook HTTP conectado con la plataforma Kommo (el BSP de WhatsApp que usa el equipo comercial).
* **Esquema de Base de Datos:** Base de datos Postgres independiente. No almacena datos en la base principal de Supabase ni en el esquema `core` del agente Meta para mantener un completo aislamiento de datos sensibles.
* **Principales Funciones:**
  * **Ingesta de Conversaciones en Tiempo Real:** Registra de manera idempotente cada evento del webhook en las tablas `kommo_accounts`, `kommo_conversations` y `kommo_messages`.
  * **Panel de Auditoría Visual:** Ofrece una interfaz de administración en `/admin/kommo/conversations` para que el supervisor o gerente pueda auditar el flujo de conversaciones de los vendedores.
  * **Análisis de Desempeño:** Procesa los datos acumulados para extraer KPIs de interacción humana que retroalimentan las estrategias del equipo comercial.

---

## 5. Supervisor del Ritmo de Ventas (Fase 2.5 de Copilot)

Es un rol especializado del **Suplai Copilot** diseñado exclusivamente para supervisores y directores de equipos de venta.

* **Propósito:** Permitir a los supervisores examinar la cadencia y periodicidad de las ventas asignadas a los diferentes preventistas del equipo.
* **Características Clave:**
  * **Análisis Temporal Dinámico:** Resuelve en tiempo real consultas sobre la venta agrupada por días de la semana (ISO Lunes=1 a Domingo=7) y la asigna al vendedor correspondiente a través del cruce de tablas `{tenant}.clients` y `vendedores_clientes`.
  * **Thought Stream (SSE de Progreso):** Implementa un flujo SSE (Server-Sent Events) que emite "pasos de progreso" determinísticos a la UI (por ejemplo, *"Consultando ventas de la semana..."* o *"Calculando ranking por vendedor..."*) para guiar al supervisor durante consultas complejas.
  * **Chips de Follow-up Contextuales:** Tras una respuesta del ritmo de ventas, el sistema genera sugerencias rápidas e interactivas (ej. *“¿Cómo fue el desglose para el vendedor X?”*, *“¿Generar reporte PDF?”*).

---

## Tabla Resumen de Agentes de Suplai Sales

| Agente / Componente | Stack Técnico | Canal de Comunicación | Tipo de Acceso a BD | Audiencia Principal | Rol Clave |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Agente Conversacional B2B** | Python, FastAPI, LangGraph | WhatsApp (Meta Cloud API) | Directo (Supabase) | Puntos de Venta (PdV) y vendedores en ruta | Automatización de pedidos y consultas |
| **Suplai Copilot** | FastAPI, Next.js, OpenAI | Panel Web (Back Office Canvas) | Directo (Supabase core + tenant) | Operadores del back office, gerentes, supervisores | Analista comercial interactivo y automatizador de agenda |
| **Sales Engine (ML)** | Python, FastAPI, scikit-learn | API REST interna | Directo (Supabase tenant) | Motores internos (B2B Agent / API) | Generador de recomendaciones y combos automáticos |
| **Sniffer Vendedores** | Python, FastAPI, Alembic | Webhook Kommo CRM | Espejo Postgres dedicado (independiente) | Supervisores y auditores comerciales | Monitoreo y auditoría de la fuerza de venta externa |
| **Supervisor de Ritmo de Ventas** | FastAPI, Next.js (Módulo Copilot) | Panel Web (Back Office) | Directo (Supabase core + tenant) | Jefes de Venta / Supervisores | Analítica temporal y de preventistas por día de la semana |

---

*Documento informativo de arquitectura y producto del ecosistema Suplai Sales. Generado el 04 de Agosto de 2026.*
