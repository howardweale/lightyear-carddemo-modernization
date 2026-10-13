packer {
  required_version = "= 1.14.2"
  required_plugins {
    googlecompute = {
      version = "= 1.2.7"
      source  = "github.com/hashicorp/googlecompute"
    }
  }
}
variable "project_id" { type = string }
variable "zone" { type = string }
variable "base_image_name" { type = string }
variable "base_image_project" { type = string }
variable "base_image_id" { type = string }
variable "builder_service_account" { type = string }
variable "builder_subnetwork" { type = string }
variable "image_name" { type = string }
variable "bundle_path" { type = string }
variable "bundle_manifest_sha256" { type = string }
variable "source_commit" { type = string }

source "googlecompute" "runner" {
  project_id              = var.project_id
  zone                    = var.zone
  source_image            = var.base_image_name
  source_image_project_id = [var.base_image_project]
  image_name              = var.image_name
  image_description       = "Lightyear reviewed offline runtime bundle ${var.bundle_manifest_sha256}"
  machine_type            = "n2-standard-4"
  disk_size               = 100
  disk_type               = "pd-balanced"
  ssh_username            = "packer"
  service_account_email   = var.builder_service_account
  subnetwork              = var.builder_subnetwork
  omit_external_ip        = true
  use_internal_ip         = true
  use_iap                 = true
  image_labels = {
    purpose = "lightyear-cloud-runner"
    commit  = var.source_commit
  }
  # Separate approved builder network/IAP access is required. The sealed runner
  # foundation deliberately has no SSH ingress and cannot be used to build.
}

build {
  sources = ["source.googlecompute.runner"]
  provisioner "shell" {
    inline = ["mkdir -p /tmp/lightyear-bundle"]
  }
  provisioner "file" {
    source      = "${var.bundle_path}/"
    destination = "/tmp/lightyear-bundle"
  }
  provisioner "file" {
    source      = "../../../tools/check_cloud_image_bundle.py"
    destination = "/tmp/check_cloud_image_bundle.py"
  }
  provisioner "shell" {
    environment_vars = [
      "BUNDLE_MANIFEST_SHA256=${var.bundle_manifest_sha256}"
    ]
    script = "install-offline.sh"
  }
  post-processor "manifest" {
    output = "packer-manifest.json"
    custom_data = {
      base_image_id          = var.base_image_id
      bundle_manifest_sha256 = var.bundle_manifest_sha256
      source_commit          = var.source_commit
    }
  }
}
