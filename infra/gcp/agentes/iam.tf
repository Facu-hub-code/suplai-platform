# Identidades del equipo de agentes (spec 138).

# --- agente-run: la identidad del contenedor de cada run ---------------------
# Puede llamar a Claude en Vertex y escribir logs. Nada más: en particular, ningún
# permiso sobre el bucket de datos. El bot baja archivos solo con la URL firmada
# que le da el MCP, así que no puede listar ni leer datos de otra distribuidora.
resource "google_service_account" "agente_run" {
  project      = var.project_id
  account_id   = "agente-run"
  display_name = "Contenedor de un run de un bot"
  description  = "Identidad del Cloud Run job agente-run. Solo Vertex y logs."
}

resource "google_project_iam_member" "agente_run" {
  for_each = toset([
    "roles/aiplatform.user",   # llamar a los modelos de Vertex
    "roles/logging.logWriter", # escribir logs del run
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.agente_run.email}"
}

# --- railway-lanzador: la identidad del backend de Railway -------------------
# Lanza, consulta y cancela ejecuciones del job, y sube y firma archivos del bucket
# de datos. No puede crear ni cambiar el job.
resource "google_service_account" "railway_lanzador" {
  project      = var.project_id
  account_id   = "railway-lanzador"
  display_name = "Backend de Railway"
  description  = "Lanza runs del job agente-run y firma URLs del bucket de datos."
}

# Rol propio con lo justo para manejar ejecuciones. Se asigna sobre el job (no sobre
# el proyecto) cuando exista el job, en el próximo paso.
resource "google_project_iam_custom_role" "lanzador_runs" {
  project     = var.project_id
  role_id     = "lanzadorRuns"
  title       = "Lanzador de runs de agentes"
  description = "Ejecutar el job con overrides, ver y cancelar sus ejecuciones."
  permissions = [
    "run.jobs.runWithOverrides",
    "run.executions.get",
    "run.executions.cancel",
    "run.operations.get",
  ]
}

# Clave de railway-lanzador: la organización bloquea crear claves de cuentas de
# servicio (iam.disableServiceAccountKeyCreation). Cómo se autentica Railway se
# decide al conectar el backend (fase 4 del spec 138). Ninguna clave pasa por este
# código: si se crea una, no debe quedar en el estado de Terraform.
