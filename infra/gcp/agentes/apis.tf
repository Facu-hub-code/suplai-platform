# APIs que usa el equipo de agentes (spec 138). Las de arranque (iam, iamcredentials,
# cloudresourcemanager, serviceusage, storage, dns) se prendieron a mano y no se repiten acá.
locals {
  apis = [
    "run.googleapis.com",              # Cloud Run jobs
    "artifactregistry.googleapis.com", # imágenes del contenedor
    "aiplatform.googleapis.com",       # Vertex AI (Claude)
    "secretmanager.googleapis.com",    # secreto HMAC del aviso de fin
    "compute.googleapis.com",          # VPC, Cloud NAT y firewall de salida
    "logging.googleapis.com",          # logs del job
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  project = var.project_id
  service = each.value

  # Si algún día se borra este recurso, no apagar la API: apagarla puede romper
  # otros recursos que la usan.
  disable_on_destroy = false
}
