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
