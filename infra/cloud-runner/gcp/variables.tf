variable "project_id" {
  type        = string
  description = "Existing, explicitly approved project; customer projects host their own data."
}
variable "region" {
  type    = string
  default = "us-west1"
}
variable "prefix" {
  type    = string
  default = "lightyear-runner"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,18}$", var.prefix))
    error_message = "Use a 3-19 character resource prefix."
  }
}
variable "inputs_bucket" {
  type = string
}
variable "evidence_bucket" {
  type = string
}
variable "repository_id" {
  type        = string
  description = "Numeric GitHub repository ID, not a reusable repository name."
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.repository_id))
    error_message = "A numeric repository ID is required."
  }
}
variable "repository_owner_id" {
  type = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.repository_owner_id))
    error_message = "A numeric owner ID is required."
  }
}
variable "workflow_ref" {
  type        = string
  description = "Exact owner/repo/.github/workflows/cloud-runner-launch.yml@refs/heads/BRANCH."
}
variable "repository" {
  type        = string
  description = "owner/repo for the protected-environment OIDC subject."
}
variable "launcher_ref" {
  type    = string
  default = "refs/heads/main"
}
variable "retention_seconds" {
  type    = number
  default = 31536000
  validation {
    condition     = var.retention_seconds >= 31536000 && floor(var.retention_seconds) == var.retention_seconds
    error_message = "Evidence retention must be at least 365 days."
  }
}
variable "phase2_approved" {
  type        = bool
  default     = false
  description = "Set only after a separate stand-up approval. Phase 1 never applies."
}
variable "lock_retention" {
  type        = bool
  default     = false
  description = "IRREVERSIBLE. Approve explicitly after checking billing, retention and a canary bucket."
}
variable "enable_federation" {
  type        = bool
  default     = false
  description = "Stays disabled during Phase 1; enabling does not grant VM creation or signing."
}
