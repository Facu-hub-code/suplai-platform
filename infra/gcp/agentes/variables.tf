variable "project_id" {
  description = "Proyecto de GCP del equipo de agentes."
  type        = string
  default     = "suplai-agentes"
}

variable "region" {
  description = "Región de Cloud Run, Artifact Registry y los buckets. Cerca de Supabase (Suplai-east)."
  type        = string
  default     = "us-east4"
}

variable "mcp_hosts" {
  description = "Host del MCP de agentes en Railway y sus alias (CNAME). Son los únicos destinos de internet que el contenedor puede alcanzar. Cloud NGFW pide listar todos los alias."
  type        = list(string)
  default     = ["mcp.suplaisales.com", "htqgvspo.up.railway.app"]
}

variable "imagen_run" {
  description = "Imagen del contenedor del run, fijada por digest. agente-run:prueba-red-v2 = prueba de red sin harness, espera la red al arrancar."
  type        = string
  default     = "us-east4-docker.pkg.dev/suplai-agentes/agentes/agente-run@sha256:ed3ca7ef3f0a2fe58546103d3bb9cf072f0d477dcee167ea58154757bda11e14"
}

variable "terraform_sa" {
  description = "Cuenta de servicio que suplanta Terraform. Se creó a mano en el arranque."
  type        = string
  default     = "terraform@suplai-agentes.iam.gserviceaccount.com"
}
