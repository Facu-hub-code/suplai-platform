# Qué versión de Terraform y de proveedor usamos, y dónde vive el estado.
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  # El estado se guarda en el bucket creado a mano (no lo maneja este código).
  # Terraform suplanta a la cuenta terraform para leerlo y escribirlo.
  backend "gcs" {
    bucket                      = "suplai-agentes-tfstate"
    prefix                      = "agentes"
    impersonate_service_account = "terraform@suplai-agentes.iam.gserviceaccount.com"
  }
}
