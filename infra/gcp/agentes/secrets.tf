# Secretos del equipo de agentes. Terraform crea el secreto vacío y los permisos;
# el valor se carga a mano con gcloud, así nunca pasa por el repo ni por el estado.

# Clave de la API de Anthropic, mientras Vertex no tenga cuota de Claude.
# Cargar el valor:
#   pbpaste | gcloud secrets versions add anthropic-api-key --project=suplai-agentes --data-file=-
resource "google_secret_manager_secret" "anthropic_api_key" {
  project   = var.project_id
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }

  labels = {
    uso = "modelo-temporal"
  }

  depends_on = [google_project_service.apis]
}

# Solo el contenedor del run la puede leer, y solo este secreto.
resource "google_secret_manager_secret_iam_member" "anthropic_agente_run" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.anthropic_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agente_run.email}"
}
