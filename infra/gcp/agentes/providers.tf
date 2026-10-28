# El proveedor de Google: a qué proyecto y región apunta, y como quién trabaja.
# Usa tu ADC para suplantar a la cuenta terraform; nunca opera con tus permisos de usuario.
provider "google" {
  project                     = var.project_id
  region                      = var.region
  impersonate_service_account = var.terraform_sa
}
