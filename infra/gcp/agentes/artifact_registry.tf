# Repositorio Docker donde se publica la imagen del run (agentes-runtime/).
resource "google_artifact_registry_repository" "agentes" {
  project       = var.project_id
  location      = var.region
  repository_id = "agentes"
  format        = "DOCKER"
  description   = "Imagen del contenedor que corre cada run de un bot."

  depends_on = [google_project_service.apis]
}

output "imagen_base" {
  description = "Prefijo para etiquetar y subir la imagen del run."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agentes.repository_id}"
}
