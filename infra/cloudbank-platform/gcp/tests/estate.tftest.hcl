mock_provider "google" {}

variables {
  project_id          = "offline-cloudbank"
  project_number      = "123456789"
  image_signer_member = "user:operator@example.invalid"
  delegated_dns_name  = "test.example.invalid"
  tls_hostname        = "cloudbank.test.example.invalid"
}

run "no_live_authority_by_default" {
  command         = plan
  expect_failures = [terraform_data.approval]
}

run "mock_estate_plan" {
  command = plan
  variables {
    live_apply_approved = true
  }
  assert {
    condition     = length(google_container_cluster.estate.node_locations) == 3 && google_container_cluster.estate.datapath_provider == "ADVANCED_DATAPATH"
    error_message = "Regional three-zone Dataplane V2 is required."
  }
  assert {
    condition     = google_container_cluster.estate.private_cluster_config[0].enable_private_nodes && !google_container_cluster.estate.control_plane_endpoints_config[0].ip_endpoints_config[0].enabled
    error_message = "Private nodes and DNS-only control plane are required."
  }
  assert {
    condition     = output.platform_infrastructure.workload_pool == "offline-cloudbank.svc.id.goog" && output.platform_infrastructure.prometheus
    error_message = "Workload Identity and managed Prometheus must be declared."
  }
  assert {
    condition     = length(google_secret_manager_secret.service) == 8 && length(google_secret_manager_secret_iam_member.reader) == 8 && length(google_project_iam_member.telemetry) == 3
    error_message = "Secret and telemetry prerequisites must cover the bootstrap estate."
  }
  assert {
    condition     = output.platform_infrastructure.sql.availability == "REGIONAL" && output.platform_infrastructure.sql.private && output.platform_infrastructure.sql.pitr && output.platform_infrastructure.sql.retained_backups == 7 && output.platform_infrastructure.sql.transaction_log_days == 7
    error_message = "Cloud SQL HA, private access and retained recovery configuration differ."
  }
  assert {
    condition     = google_container_cluster.estate.node_pool[0].initial_node_count == 1 && google_container_cluster.estate.node_pool[0].autoscaling[0].max_node_count == 2
    error_message = "Per-zone bootstrap capacity must be preserved."
  }
  assert {
    condition     = output.platform_infrastructure.live_drills == "NOT RUN" && !output.platform_infrastructure.qualified
    error_message = "A mocked plan cannot claim live qualification."
  }
}

run "reject_two_zones" {
  command = plan
  variables {
    live_apply_approved = true
    zones               = ["europe-west2-a", "europe-west2-b"]
  }
  expect_failures = [var.zones]
}
