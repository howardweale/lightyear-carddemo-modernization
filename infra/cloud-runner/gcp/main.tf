# Foundation only. There is deliberately no compute_instance, VM-create role,
# service-account impersonation of workers, project creation, or budget authority.
resource "terraform_data" "approval" {
  lifecycle {
    precondition {
      condition     = var.phase2_approved
      error_message = "Phase 2 stand-up requires Howard's separate approval; Phase 1 is offline only."
    }
    precondition {
      condition     = var.inputs_bucket != var.evidence_bucket
      error_message = "Input and evidence stores must be separate."
    }
  }
}

locals {
  scopes = toset(["engineering", "qualification", "factory"])
  keys = { for pair in setproduct(local.scopes, ["go", "witness", "ledger"]) :
    join("-", pair) => { scope = pair[0], purpose = pair[1] }
  }
}

resource "google_storage_bucket" "store" {
  for_each                    = { inputs = var.inputs_bucket, evidence = var.evidence_bucket }
  name                        = each.value
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning {
    enabled = true
  }
  retention_policy {
    retention_period = var.retention_seconds
    is_locked        = var.lock_retention
  }
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [terraform_data.approval]
}

resource "google_service_account" "launcher" {
  account_id   = "${var.prefix}-launch"
  display_name = "Cloud runner admission reader (no execution/signing authority)"
  depends_on   = [terraform_data.approval]
}
resource "google_service_account" "worker" {
  for_each     = local.scopes
  account_id   = "${var.prefix}-${substr(each.key, 0, 4)}"
  display_name = "Cloud runner ${each.key} worker (no signing authority)"
  depends_on   = [terraform_data.approval]
}
resource "google_storage_bucket_iam_member" "input_reader" {
  for_each = merge({ launcher = google_service_account.launcher.email },
  { for scope, sa in google_service_account.worker : scope => sa.email })
  bucket = google_storage_bucket.store["inputs"].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${each.value}"
}
resource "google_storage_bucket_iam_member" "evidence_writer" {
  for_each = google_service_account.worker
  bucket   = google_storage_bucket.store["evidence"].name
  role     = "roles/storage.objectCreator"
  member   = "serviceAccount:${each.value.email}"
  condition {
    title       = "scope-evidence-only"
    description = "Workers only append in their own scope."
    expression  = "resource.name.startsWith('projects/_/buckets/${var.evidence_bucket}/objects/${each.key}/')"
  }
}
resource "google_project_iam_member" "worker_logging" {
  for_each = google_service_account.worker
  project  = var.project_id
  role     = "roles/logging.logWriter"
  member   = "serviceAccount:${each.value.email}"
}

resource "google_kms_key_ring" "runner" {
  name       = var.prefix
  location   = var.region
  depends_on = [terraform_data.approval]
}
resource "google_kms_crypto_key" "signing" {
  for_each                   = local.keys
  name                       = each.key
  key_ring                   = google_kms_key_ring.runner.id
  purpose                    = "ASYMMETRIC_SIGN"
  destroy_scheduled_duration = "2592000s"
  version_template {
    algorithm        = "EC_SIGN_ED25519"
    protection_level = "SOFTWARE"
  }
  lifecycle {
    prevent_destroy = true
  }
  # No signing IAM grants here. Go, witness and cleanup-ledger service admission
  # must be reviewed in Phase 2. Neither workers nor launcher can forge a go.
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.prefix
  disabled                  = !var.enable_federation
  depends_on                = [terraform_data.approval]
}
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  disabled                           = !var.enable_federation
  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
  }
  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.repository_id}'",
    "assertion.repository_owner_id == '${var.repository_owner_id}'",
    "assertion.workflow_ref == '${var.workflow_ref}'",
    "assertion.ref == '${var.launcher_ref}'",
    "assertion.event_name == 'workflow_dispatch'",
    "assertion.sub == 'repo:${var.repository}:environment:cloud-runner-admission'"
  ])
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}
resource "google_service_account_iam_member" "launcher_federation" {
  service_account_id = google_service_account.launcher.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.repository_id}"
}

resource "google_compute_network" "runner" {
  name                    = var.prefix
  auto_create_subnetworks = false
  depends_on              = [terraform_data.approval]
}
resource "google_compute_subnetwork" "runner" {
  name                     = var.prefix
  region                   = var.region
  ip_cidr_range            = "10.71.0.0/24"
  network                  = google_compute_network.runner.id
  private_ip_google_access = true
}
resource "google_compute_firewall" "deny_ingress" {
  name          = "${var.prefix}-deny-ingress"
  network       = google_compute_network.runner.name
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "all"
  }
}
resource "google_compute_firewall" "google_api_egress" {
  name               = "${var.prefix}-google-api-egress"
  network            = google_compute_network.runner.name
  direction          = "EGRESS"
  priority           = 1000
  destination_ranges = ["199.36.153.8/30"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}
resource "google_compute_firewall" "deny_egress" {
  name               = "${var.prefix}-deny-egress"
  network            = google_compute_network.runner.name
  direction          = "EGRESS"
  priority           = 2000
  destination_ranges = ["0.0.0.0/0"]
  deny {
    protocol = "all"
  }
}
resource "google_dns_managed_zone" "googleapis" {
  name       = "${var.prefix}-googleapis"
  dns_name   = "googleapis.com."
  visibility = "private"
  private_visibility_config {
    networks {
      network_url = google_compute_network.runner.id
    }
  }
}
resource "google_dns_record_set" "api_vip" {
  name         = "private.googleapis.com."
  managed_zone = google_dns_managed_zone.googleapis.name
  type         = "A"
  ttl          = 300
  rrdatas      = ["199.36.153.8", "199.36.153.9", "199.36.153.10", "199.36.153.11"]
}
resource "google_dns_record_set" "api_alias" {
  name         = "*.googleapis.com."
  managed_zone = google_dns_managed_zone.googleapis.name
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["private.googleapis.com."]
}
