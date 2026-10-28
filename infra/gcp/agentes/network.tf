# Red de salida cerrada del contenedor (spec 138, «Red»).
# El job manda todo su tráfico a esta VPC. Desde acá solo puede llegar a las APIs de
# Google por la ruta privada y al MCP de agentes por NAT. Todo lo demás se bloquea.

resource "google_compute_network" "agentes" {
  project                 = var.project_id
  name                    = "agentes"
  auto_create_subnetworks = false # las subredes las definimos nosotros

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "run" {
  project       = var.project_id
  name          = "agentes-run"
  network       = google_compute_network.agentes.id
  region        = var.region
  ip_cidr_range = "10.10.0.0/24"

  # Llegar a Vertex y Storage sin IP pública y sin pasar por internet.
  private_ip_google_access = true
}

# --- Salida a internet: solo por NAT (el contenedor no tiene IP pública) -------
resource "google_compute_router" "agentes" {
  project = var.project_id
  name    = "agentes-router"
  network = google_compute_network.agentes.id
  region  = var.region
}

resource "google_compute_router_nat" "agentes" {
  project                            = var.project_id
  name                               = "agentes-nat"
  router                             = google_compute_router.agentes.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.run.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY" # queda registro de lo que el firewall o NAT rechazan
  }
}

# --- DNS privado: *.googleapis.com resuelve al rango privado de Google ---------
# private.googleapis.com = 199.36.153.8/30. Así el firewall solo tiene que permitir
# ese rango para Vertex y Storage.
locals {
  google_privado = ["199.36.153.8", "199.36.153.9", "199.36.153.10", "199.36.153.11"]
}

resource "google_dns_managed_zone" "googleapis" {
  project     = var.project_id
  name        = "googleapis-privado"
  dns_name    = "googleapis.com."
  description = "googleapis.com por la ruta privada, solo dentro de la VPC agentes."
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.agentes.id
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_dns_record_set" "googleapis_a" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  name         = "private.googleapis.com."
  type         = "A"
  ttl          = 300
  rrdatas      = local.google_privado
}

resource "google_dns_record_set" "googleapis_cname" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.googleapis.name
  name         = "*.googleapis.com."
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["private.googleapis.com."]
}

# --- Firewall: qué puede salir ----------------------------------------------
# Política de firewall de red: se evalúa antes que las reglas clásicas de la VPC.
# En la VPC solo corre el job, por eso las reglas no necesitan objetivo.
resource "google_compute_network_firewall_policy" "salida" {
  project     = var.project_id
  name        = "agentes-salida"
  description = "El contenedor solo sale a Google (ruta privada) y al MCP de agentes."
}

resource "google_compute_network_firewall_policy_rule" "google_privado" {
  project         = var.project_id
  firewall_policy = google_compute_network_firewall_policy.salida.name
  priority        = 1000
  direction       = "EGRESS"
  action          = "allow"
  description     = "Vertex y Cloud Storage por private.googleapis.com."
  enable_logging  = false

  match {
    dest_ip_ranges = ["199.36.153.8/30"]
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["443"]
    }
  }
}

resource "google_compute_network_firewall_policy_rule" "mcp" {
  project         = var.project_id
  firewall_policy = google_compute_network_firewall_policy.salida.name
  priority        = 1100
  direction       = "EGRESS"
  action          = "allow"
  description     = "MCP de agentes en Railway, por nombre de dominio y sus alias."
  enable_logging  = false

  match {
    dest_fqdns = var.mcp_hosts
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["443"]
    }
  }
}

resource "google_compute_network_firewall_policy_rule" "anthropic" {
  project         = var.project_id
  firewall_policy = google_compute_network_firewall_policy.salida.name
  priority        = 1200
  direction       = "EGRESS"
  action          = "allow"
  description     = "API de Anthropic, mientras Vertex no tenga cuota de Claude. Se borra al volver a Vertex."
  enable_logging  = false

  match {
    dest_fqdns = var.anthropic_hosts
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["443"]
    }
  }
}

resource "google_compute_network_firewall_policy_rule" "bloquear_resto" {
  project         = var.project_id
  firewall_policy = google_compute_network_firewall_policy.salida.name
  priority        = 65000
  direction       = "EGRESS"
  action          = "deny"
  description     = "Todo lo demás, bloqueado. Queda en el log."
  enable_logging  = true

  match {
    dest_ip_ranges = ["0.0.0.0/0"]
    layer4_configs {
      ip_protocol = "all"
    }
  }
}

resource "google_compute_network_firewall_policy_association" "salida" {
  project           = var.project_id
  name              = "agentes-salida"
  firewall_policy   = google_compute_network_firewall_policy.salida.id
  attachment_target = google_compute_network.agentes.id
}
