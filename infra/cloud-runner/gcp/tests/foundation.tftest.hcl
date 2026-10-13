mock_provider "google" {}

variables {
  project_id          = "offline-test-project"
  inputs_bucket       = "offline-test-inputs"
  evidence_bucket     = "offline-test-evidence"
  repository_id       = "123456"
  repository_owner_id = "456789"
  repository          = "test-owner/test-repo"
  workflow_ref        = "test-owner/test-repo/.github/workflows/cloud-runner-launch.yml@refs/heads/main"
}

run "stand_up_requires_approval" {
  command         = plan
  expect_failures = [terraform_data.approval]
}

run "offline_foundation_contract" {
  command = plan
  variables {
    phase2_approved = true
  }
  assert {
    condition     = google_iam_workload_identity_pool.github.disabled
    error_message = "Federation must stay disabled by default."
  }
  assert {
    condition     = google_storage_bucket.store["evidence"].retention_policy[0].retention_period >= 31536000 && !google_storage_bucket.store["evidence"].force_destroy
    error_message = "Evidence retention weakened."
  }
  assert {
    condition     = alltrue([for k in google_kms_crypto_key.signing : k.version_template[0].algorithm == "EC_SIGN_ED25519" && k.version_template[0].protection_level == "SOFTWARE"])
    error_message = "Signing algorithm or protection differs."
  }
  assert {
    condition     = length(google_kms_crypto_key.signing) == 9
    error_message = "Each scope must have distinct go, witness and ledger keys."
  }
  assert {
    condition     = !output.sealed_run_ready
    error_message = "Foundation deployment cannot authorize sealed campaigns."
  }
}
