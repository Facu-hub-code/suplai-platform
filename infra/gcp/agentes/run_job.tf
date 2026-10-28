# El Cloud Run job: la plantilla de un run. Cada ejecución es un contenedor nuevo
# que corre un solo bot y se destruye al terminar (spec 138).
resource "google_cloud_run_v2_job" "agente_run" {
  project  = var.project_id
  name     = "agente-run"
  location = var.region

  # POC: permite borrarlo y recrearlo mientras aprendemos.
  deletion_protection = false

  template {
    task_count  = 1 # un run = una tarea
    parallelism = 1

    template {
      service_account = google_service_account.agente_run.email
      max_retries     = 0       # los reintentos los decide el backend
      timeout         = "7200s" # 2 h; cada ejecución lo puede bajar con overrides

      containers {
        image = var.imagen_run

        # Defaults de cada run. El backend los pisa con overrides al lanzar.
        env {
          name  = "PROVEEDOR_MODELO"
          value = var.proveedor_modelo
        }
        env {
          name  = "MODELO"
          value = "claude-opus-5-5"
        }
        env {
          name  = "TOPE_USD"
          value = "1.0"
        }
        env {
          name  = "MCP_HOST"
          value = var.mcp_hosts[0]
        }

        # La clave la busca Cloud Run en Secret Manager al arrancar cada ejecución.
        # En la configuración del job solo queda la referencia, nunca el valor.
        env {
          name = "ANTHROPIC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.anthropic_api_key.secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }

      # Todo el tráfico de salida va a la VPC cerrada (network.tf).
      vpc_access {
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = google_compute_network.agentes.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_compute_network_firewall_policy_association.salida,
    google_secret_manager_secret_iam_member.anthropic_agente_run,
  ]
}

# railway-lanzador puede ejecutar, ver y cancelar ejecuciones de este job, y nada más.
resource "google_cloud_run_v2_job_iam_member" "lanzador" {
  project  = var.project_id
  location = google_cloud_run_v2_job.agente_run.location
  name     = google_cloud_run_v2_job.agente_run.name
  role     = google_project_iam_custom_role.lanzador_runs.id
  member   = "serviceAccount:${google_service_account.railway_lanzador.email}"
}
