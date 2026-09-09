"""Explicit MS67 application identities without changing the MS65 contract.

The live executor converges forward, one deployment at a time. Its only patches
set the main container's user and primary group; it never replaces a pod template
or scales an application down. Interrupted runs can be retried with fresh output.
"""
from __future__ import annotations

import copy
import json
import re

from .cloudbank_image_security import stamp
from .cloudbank_journeys import SERVICES, hashed, require
from .contracts import content_hash, verify_signature

IDENTITY = {"runAsUser": 65532, "runAsGroup": 65532}
OBSERVATION_TYPE = "lightyear-cloudbank-ms67-runtime-identity-observation"
OBSERVATION_FILE = "runtime-identity.observation.json"
STATE_FILE = "runtime-identity.state.json"
PASS = "passed-eight-runtime-identities"


def container(deployment, service, namespace, image=None):
    """Require the existing bounded rollout and sandbox before adding IDs."""
    meta, spec = deployment.get("metadata", {}), deployment.get("spec", {})
    require(deployment.get("apiVersion") == "apps/v1" and deployment.get("kind") == "Deployment"
            and service in SERVICES and meta.get("name") == service and meta.get("namespace") == namespace,
            "runtime-identity-deployment-scope-invalid")
    strategy = spec.get("strategy", {})
    require(spec.get("replicas") == 2 and strategy.get("type") == "RollingUpdate"
            and strategy.get("rollingUpdate") == {"maxSurge": 1, "maxUnavailable": 0},
            "runtime-identity-bounded-rolling-update-required")
    pod = spec.get("template", {}).get("spec", {})
    rows = pod.get("containers", [])
    require(len(rows) == 1 and rows[0].get("name") == service
            and not pod.get("initContainers") and not pod.get("ephemeralContainers"),
            "runtime-identity-single-application-container-required")
    main = rows[0]
    require(re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", main.get("image", ""))
            and (image is None or main["image"] == image), "runtime-identity-image-drift")
    security = main.get("securityContext", {})
    effective = {**pod.get("securityContext", {}), **security}
    require(pod.get("automountServiceAccountToken") is False and effective.get("runAsNonRoot") is True
            and security.get("allowPrivilegeEscalation") is False
            and security.get("readOnlyRootFilesystem") is True and not security.get("privileged")
            and security.get("capabilities", {}).get("drop") == ["ALL"]
            and not security.get("capabilities", {}).get("add")
            and effective.get("seccompProfile") == {"type": "RuntimeDefault"},
            "runtime-identity-existing-sandbox-required")
    return main


def target(deployment, service, namespace, image=None):
    result = copy.deepcopy(deployment)
    container(result, service, namespace, image)["securityContext"].update(IDENTITY)
    return result


def instrument_bundle(bundle, namespace):
    require(bundle.get("kind") == "List" and isinstance(bundle.get("items"), list),
            "runtime-identity-list-required")
    result, seen = copy.deepcopy(bundle), set()
    for row in result["items"]:
        if row.get("kind") != "Deployment":
            continue
        service = row.get("metadata", {}).get("name")
        require(service in SERVICES and service not in seen, "runtime-identity-deployment-set-invalid")
        container(row, service, namespace)["securityContext"].update(IDENTITY)
        seen.add(service)
    require(seen == set(SERVICES), "runtime-identity-eight-deployments-required")
    return result


def deployment_patch(deployment, service, namespace, image, baseline):
    container(deployment, service, namespace, image)
    meta = deployment["metadata"]
    require(meta.get("uid") == baseline["deployment_uid"]
            and hashed(deployment["spec"]) == baseline["before_spec_sha256"],
            "runtime-identity-deployment-changed-since-preflight")
    require(bool(meta.get("uid") and meta.get("resourceVersion")), "runtime-identity-live-metadata-required")
    return [{"op": "test", "path": "/metadata/uid", "value": meta["uid"]},
            {"op": "test", "path": "/metadata/resourceVersion", "value": meta["resourceVersion"]},
            *[{"op": "add", "path": "/spec/template/spec/containers/0/securityContext/" + key, "value": value}
              for key, value in IDENTITY.items()]]


def pod_observation(pods, service, namespace, image, *, corrected):
    require(len(pods) == 2, "runtime-identity-two-owned-pods-required")
    uids, gids, identities = [], [], []
    for pod in pods:
        meta, spec = pod.get("metadata", {}), pod.get("spec", {})
        main, statuses = spec.get("containers", []), pod.get("status", {}).get("containerStatuses", [])
        require(meta.get("namespace") == namespace and meta.get("uid") and not meta.get("deletionTimestamp")
                and len(main) == 1 and main[0].get("name") == service and main[0].get("image") == image
                and not spec.get("initContainers") and not spec.get("ephemeralContainers")
                and len(statuses) == 1 and statuses[0].get("name") == service,
                "runtime-identity-pod-scope-invalid")
        status = statuses[0]
        identity = status.get("user", {}).get("linux", {})
        uid, gid = identity.get("uid"), identity.get("gid")
        digest = image.split("@sha256:")[1]
        image_id = status.get("imageID", "")
        require(status.get("ready") is True and "running" in status.get("state", {})
                and (image_id.endswith("@sha256:" + digest) or image_id == "containerd://sha256:" + digest),
                "runtime-identity-pod-image-or-readiness-invalid")
        require(type(uid) is int and type(gid) is int and uid == 65532 and gid in {0, 65532},
                "runtime-identity-startup-identity-unavailable-or-unexpected")
        if corrected:
            require(gid == 65532 and all(main[0].get("securityContext", {}).get(k) == v for k, v in IDENTITY.items()),
                    "runtime-identity-explicit-user-and-group-not-observed")
        uids.append(uid)
        gids.append(gid)
        identities.append(hashed(meta["uid"]))
    require(len(set(identities)) == 2, "runtime-identity-distinct-owned-pods-required")
    return {"ready_replicas": 2, "startup_uids": uids, "startup_gids": gids,
            "pod_uid_sha256": sorted(identities), "image": image}


class IdentityRollout:
    def __init__(self, runtime, journal, state, progress=lambda _: None):
        self.r, self.journal, self.s, self.progress = runtime, journal, state, progress

    def inspect(self, service, *, corrected):
        deploy = self.r.deployment(service)
        container(deploy, service, self.r.namespace, self.r.images[service])
        self.r.service_ready(service)
        result = pod_observation(self.r.pods(service), service, self.r.namespace, self.r.images[service], corrected=corrected)
        self.r.close_forward(service)
        response = self.r.send(service, "GET", "/actuator/health/readiness", None, {})
        require(response.status == 200 and response.json().get("status") == "UP", "runtime-identity-http-readiness-failed")
        result.update(http_readiness=200, deployment_uid=deploy["metadata"]["uid"],
                      deployment_spec_sha256=hashed(deploy["spec"]), observed_at=stamp())
        return result

    def preflight(self):
        self.s["baseline"], self.s["services"] = {}, {}
        # Finish checking every service before the first journal or patch.
        for service in SERVICES:
            self.progress("Checking runtime identity and readiness: " + service)
            deploy = self.r.deployment(service)
            expected = target(deploy, service, self.r.namespace, self.r.images[service])
            configured = deploy["spec"] == expected["spec"]
            if configured:
                # A previous disconnected run may already have submitted this patch.
                self.r.wait_ready(service)
            self.s["baseline"][service] = {
                "deployment_uid": deploy["metadata"]["uid"], "before_spec_sha256": hashed(deploy["spec"]),
                "target_spec_sha256": hashed(expected["spec"]), "already_configured": configured,
                "before": self.inspect(service, corrected=configured)}
        return self.s["baseline"]

    def save(self, phase):
        self.s.update(phase=phase, updated_at=stamp())
        self.journal.write(self.s)

    def run(self):
        self.preflight()
        for service in SERVICES:
            self.progress("Enforcing and verifying 65532:65532: " + service)
            baseline = self.s["baseline"][service]
            deploy = self.r.deployment(service)
            require(deploy["metadata"]["uid"] == baseline["deployment_uid"], "runtime-identity-deployment-replaced")
            if hashed(deploy["spec"]) != baseline["target_spec_sha256"]:
                patch = deployment_patch(deploy, service, self.r.namespace, self.r.images[service], baseline)
                self.save("before-patch-" + service)
                self.r.kubectl("patch", "deployment/" + service, "--type=json", "--patch", json.dumps(patch))
            self.r.wait_ready(service)
            row = self.inspect(service, corrected=True)
            require(row["deployment_spec_sha256"] == baseline["target_spec_sha256"], "runtime-identity-post-patch-spec-drift")
            self.s["services"][service] = row
            self.save("verified-" + service)
        # Catch drift in an earlier deployment before producing the final observation.
        for service in SERVICES:
            row = self.inspect(service, corrected=True)
            require(row["deployment_uid"] == self.s["baseline"][service]["deployment_uid"]
                    and row["deployment_spec_sha256"] == self.s["baseline"][service]["target_spec_sha256"],
                    "runtime-identity-final-deployment-drift")
            self.s["services"][service] = row
        self.save("all-eight-verified")
        return {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "status": PASS,
                "run_id": self.s["run_id"], "environment": self.s["environment"], "bindings": self.s["bindings"],
                "images": self.r.images, "baseline": self.s["baseline"], "services": self.s["services"],
                "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False,
                "ms67_complete": False, "production_ready": False}


def verify_observation(value, key, bindings, images, environment):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "runtime-identity-observation-signature-invalid")
    require(value.get("schema_version") == "1.0" and value.get("observation_type") == OBSERVATION_TYPE
            and value.get("status") == PASS and re.fullmatch(r"ms67-identity-[0-9a-f]{32}", value.get("run_id", ""))
            and all(value.get(k) is False for k in ("credentials_persisted", "raw_output_persisted", "production_environment",
                                                   "ms67_complete", "production_ready")),
            "runtime-identity-passing-bounded-observation-required")
    require(value.get("bindings") == bindings and value.get("images") == images
            and all(value.get("environment", {}).get(k) == v for k, v in environment.items()),
            "runtime-identity-observation-bindings-invalid")
    require(set(value.get("services", {})) == set(SERVICES) and set(value.get("baseline", {})) == set(SERVICES),
            "runtime-identity-eight-verified-services-required")
    for service in SERVICES:
        row, baseline = value["services"][service], value["baseline"][service]
        require(row.get("ready_replicas") == 2 and row.get("http_readiness") == 200
                and row.get("startup_uids") == [65532, 65532] and row.get("startup_gids") == [65532, 65532]
                and row.get("image") == images[service] and row.get("deployment_uid") == baseline.get("deployment_uid")
                and row.get("deployment_spec_sha256") == baseline.get("target_spec_sha256")
                and bool(row.get("deployment_uid")) and bool(row.get("observed_at"))
                and re.fullmatch(r"[0-9a-f]{64}", row.get("deployment_spec_sha256", ""))
                and len(row.get("pod_uid_sha256", [])) == 2 and len(set(row["pod_uid_sha256"])) == 2
                and all(re.fullmatch(r"[0-9a-f]{64}", item) for item in row["pod_uid_sha256"]),
                "runtime-identity-service-evidence-incomplete")
