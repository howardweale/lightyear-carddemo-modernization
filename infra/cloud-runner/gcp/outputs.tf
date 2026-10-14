output "stores" {
  value = { for key, bucket in google_storage_bucket.store : key => bucket.name }
}
output "kms_keys" {
  description = "Resolve and review numeric key versions and public fingerprints before activation."
  value       = { for key, resource in google_kms_crypto_key.signing : key => resource.id }
}
output "federation_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
output "launcher_service_account" {
  value = google_service_account.launcher.email
}
output "worker_service_accounts" {
  value = { for key, sa in google_service_account.worker : key => sa.email }
}
output "subnetwork" {
  value = google_compute_subnetwork.runner.id
}
output "sealed_run_ready" {
  value = false
}
