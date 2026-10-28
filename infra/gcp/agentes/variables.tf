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

variable "anthropic_hosts" {
  description = "API de Anthropic. Destino temporal mientras Vertex no tenga cuota de Claude."
  type        = list(string)
  default     = ["api.anthropic.com"]
}

variable "imagen_run" {
  description = "Imagen del contenedor del run, fijada por digest. agente-run:harness-v2 = Claude Agent SDK conectado a /agentes/mcp."
  type        = string
  default     = "us-east4-docker.pkg.dev/suplai-agentes/agentes/agente-run@sha256:0dcc180abaffca0d048f4b98e974a9ea41e3fad0baa350d643ac05f8f961fa6e"
}

variable "proveedor_modelo" {
  description = "anthropic (API directa, mientras Vertex no tenga cuota de Claude) o vertex."
  type        = string
  default     = "anthropic"
}

variable "terraform_sa" {
  description = "Cuenta de servicio que suplanta Terraform. Se creó a mano en el arranque."
  type        = string
  default     = "terraform@suplai-agentes.iam.gserviceaccount.com"
}
