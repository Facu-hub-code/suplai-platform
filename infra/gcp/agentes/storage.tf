# Bucket de los archivos de exportar_lote y guardar_archivo (spec 139).
# Rutas: {schema}/{trabajo_id}/{run_id}/archivo. Datos de clientes: privado y efímero.
resource "google_storage_bucket" "datos" {
  project  = var.project_id
  name     = "suplai-agentes-datos"
  location = var.region

  uniform_bucket_level_access = true       # permisos del bucket entero, no por archivo
  public_access_prevention    = "enforced" # nunca público, ni por error

  # Si el bucket tiene archivos, terraform destroy falla en vez de borrarlos.
  force_destroy = false

  # Cada archivo se borra solo a los 7 días.
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  # Sin papelera: un archivo borrado no se puede recuperar. Son copias de datos
  # que ya viven en Supabase; guardarlas más tiempo solo suma riesgo.
  soft_delete_policy {
    retention_duration_seconds = 0
  }

  depends_on = [google_project_service.apis]
}

# El backend sube los archivos y firma las URLs. Las URLs firmadas usan los permisos
# de quien firma, por eso railway-lanzador necesita leer y escribir objetos.
resource "google_storage_bucket_iam_member" "datos_lanzador" {
  bucket = google_storage_bucket.datos.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.railway_lanzador.email}"
}
