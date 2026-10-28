# Infraestructura del equipo de agentes (GCP)

Terraform del proyecto `suplai-agentes`. Diseño en el spec [138](../../../docs/specs/138-agentes-adaptador-runtime.md).

## Arranque (hecho a mano, una vez)

| Qué | Cómo |
|-----|------|
| Proyecto `suplai-agentes` en la organización `suplaisales.com` | `gcloud projects create` |
| Facturación `017113-F57840-D689BC` | `gcloud billing projects link` |
| APIs `iam`, `iamcredentials`, `cloudresourcemanager`, `serviceusage`, `storage` | `gcloud services enable` |
| Cuenta de servicio `terraform` con sus roles de proyecto | `gcloud iam service-accounts create` + `add-iam-policy-binding` |
| `facundo@suplaisales.com` puede suplantar a `terraform` | `roles/iam.serviceAccountTokenCreator` sobre la cuenta |
| Bucket del estado `suplai-agentes-tfstate` (us-east4, versionado) | `gcloud storage buckets create` |
| API `dns` y `roles/dns.admin` para `terraform` (zona DNS privada) | `gcloud services enable` + `add-iam-policy-binding` |

## Uso

Requiere `gcloud auth application-default login` con `facundo@suplaisales.com`.

```bash
cd infra/gcp/agentes
terraform init
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

Nunca `apply` sin revisar el `plan`.
