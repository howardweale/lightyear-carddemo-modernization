"""Concrete GKE adapter for the shared PostgreSQL target journey executor.

All kubectl calls use the explicit context. Credentials are fetched into memory,
and PostgreSQL credentials reach the temporary probe through secretKeyRef only.
"""
from __future__ import annotations

import base64
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .contracts import sign
from .cloudbank_journeys import JourneyFailure, Response, ROLE_SCOPES, SERVICES, hashed, require


# Authorization precedes its clients; Account precedes Transfer and Checks.
# TestRunner resumes after the services it exercises. Group members can start
# together, without concurrent access to the signed recovery journal.
RESTORATION_GROUPS = (
    ("azn-server",),
    ("customer", "account", "creditscore", "chatbot"),
    ("transfer", "checks"),
    ("testrunner",),
)


def command(argv: list[str], *, data: str | None = None, timeout=45) -> str:
    try:
        result = subprocess.run(argv, input=data, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise JourneyFailure("operator-command-unavailable-or-timed-out") from None
    require(result.returncode == 0, "operator-command-failed")
    require(len(result.stdout) <= 4 * 1024 * 1024, "operator-command-output-too-large")
    return result.stdout


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GkeRuntime:
    def __init__(self, *, project: str, region: str, cluster: str, namespace: str,
                 images: dict[str, str], run_id: str, output: Path, probe_image: str | None = None,
                 progress=lambda _: None, signing_key: str = "", signer: str = ""):
        for value in (project, region, cluster, namespace, run_id):
            require(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value) is not None,
                    "gke-identity-invalid")
        require(set(images) == set(SERVICES), "eight-service-image-lock-required")
        require(all(re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value) for value in images.values()),
                "immutable-service-images-required")
        if probe_image:
            require(re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", probe_image) is not None,
                    "immutable-postgresql-probe-image-required")
        self.project, self.region, self.cluster, self.namespace = project, region, cluster, namespace
        self.context = f"gke_{project}_{region}_{cluster}"
        self.images, self.run_id, self.output = images, run_id, output
        self.probe_image, self.progress = probe_image, progress
        self.probe_name = "ly-journey-probe-" + hashed(run_id)[:12]
        self.owner = ""
        self.credentials: dict = {}
        self.tokens: dict = {}
        self.forwards: dict = {}
        self.original: dict = {}
        self.stopped: set[str] = set()
        self.pod_sets: dict[str, set[str]] = {}
        self.start_counts = {s: 0 for s in SERVICES}
        self.probe_uid: str | None = None
        self.signing_key, self.signer = signing_key, signer
        self.checks_delivery: dict | None = None
        self.opener = build_opener(NoRedirect())

    def kubectl(self, *args: str, data=None, timeout=45) -> str:
        return command(["kubectl", "--context", self.context, "--request-timeout=30s",
                        "-n", self.namespace, *args], data=data, timeout=timeout)

    def get(self, kind: str, name: str | None = None, selector: str | None = None):
        args = ["get", kind]
        if name:
            args.append(name)
        if selector:
            args += ["-l", selector]
        return json.loads(self.kubectl(*args, "-o", "json"))

    def environment(self) -> dict:
        label = command(["gcloud", "projects", "describe", self.project,
                         "--format=value(labels.environment)"]).strip()
        require(label in {"non-production", "nonprod", "test", "sandbox"}, "non-production-project-required")
        ns = self.get("namespace", self.namespace)
        require(ns.get("metadata", {}).get("labels", {}).get("environment") in
                {"non-production", "nonprod", "test", "sandbox"}, "non-production-namespace-required")
        return {"project": self.project, "region": self.region, "cluster": self.cluster,
                "namespace": self.namespace, "namespace_uid_sha256": hashed(ns["metadata"]["uid"])}

    def deployment(self, service: str) -> dict:
        require(service in SERVICES, "unknown-service")
        deploy = self.get("deployment", service)
        metadata, spec = deploy.get("metadata", {}), deploy.get("spec", {})
        main = [c for c in spec.get("template", {}).get("spec", {}).get("containers", []) if c.get("name") == service]
        require(len(main) == 1 and main[0].get("image") == self.images[service], "deployment-image-drift")
        if service in self.original:
            require(metadata.get("uid") == self.original[service]["uid"], "deployment-identity-drift")
        else:
            require(spec.get("replicas") == 2, "two-replica-baseline-required")
            self.original[service] = {"uid": metadata["uid"], "replicas": 2}
        return deploy

    def pods(self, service: str) -> list[dict]:
        deploy = self.deployment(service)
        selector = "app.kubernetes.io/name=" + service
        sets = self.get("replicasets", selector=selector).get("items", [])
        owned = {s["metadata"]["uid"] for s in sets if any(
            ref.get("uid") == deploy["metadata"]["uid"] and ref.get("controller") is True
            for ref in s.get("metadata", {}).get("ownerReferences", []))}
        return [p for p in self.get("pods", selector=selector).get("items", []) if any(
            ref.get("uid") in owned and ref.get("controller") is True
            for ref in p.get("metadata", {}).get("ownerReferences", []))]

    def service_ready(self, service: str) -> dict:
        deploy = self.deployment(service)
        status, meta = deploy.get("status", {}), deploy["metadata"]
        require(deploy["spec"].get("replicas") == 2 and status.get("observedGeneration", -1) >= meta["generation"]
                and status.get("readyReplicas", 0) == 2 and status.get("updatedReplicas", 0) == 2
                and status.get("availableReplicas", 0) == 2, "service-not-ready")
        pods = self.pods(service)
        require(len(pods) == 2, "service-pod-count-not-ready")
        expected_digest = self.images[service].split("@sha256:")[1]
        for pod in pods:
            statuses = [s for s in pod.get("status", {}).get("containerStatuses", []) if s.get("name") == service]
            require(not pod.get("metadata", {}).get("deletionTimestamp") and len(statuses) == 1
                    and statuses[0].get("ready") is True and "running" in statuses[0].get("state", {})
                    and statuses[0].get("imageID", "").endswith("sha256:" + expected_digest),
                    "running-container-image-or-readiness-mismatch")
        uids = {p["metadata"]["uid"] for p in pods}
        if service not in self.pod_sets or not (self.pod_sets[service] & uids):
            self.start_counts[service] += 1
            self.pod_sets[service] = uids
        return {"image": self.images[service], "ready_replicas": 2,
                "pod_identity_sha256": hashed(sorted(uids)), "observed_start_count": self.start_counts[service]}

    def ready(self) -> dict:
        result = {}
        for service in SERVICES:
            result[service] = self.service_ready(service)
            response = self.send(service, "GET", "/actuator/health/readiness", None, {})
            require(response.status == 200 and response.json().get("status") == "UP",
                    "service-http-readiness-failed")
            result[service]["http_readiness"] = 200
        return result

    def wait_ready(self, service: str, previous: set[str] | None = None) -> None:
        deadline = time.monotonic() + 300
        while True:
            try:
                self.service_ready(service)
                if previous is None or not (previous & self.pod_sets[service]):
                    break
            except JourneyFailure as exc:
                if str(exc) in {"deployment-image-drift", "deployment-identity-drift"}:
                    raise
            require(time.monotonic() < deadline, "service-recovery-timeout")
            time.sleep(2)
        self.close_forward(service)

    def secret_json(self, name: str) -> dict:
        require(re.fullmatch(r"[a-z0-9-]{1,100}", name) is not None, "secret-reference-invalid")
        raw = command(["gcloud", "secrets", "versions", "access", "latest", "--secret", name,
                       "--project", self.project])
        try:
            value = json.loads(raw)
            require(isinstance(value, dict) and all(isinstance(v, str) for v in value.values()), "secret-json-shape-invalid")
            return value
        except (ValueError, UnicodeError):
            raise JourneyFailure("secret-json-invalid") from None

    def load_credentials(self):
        secret = self.secret_json("cloudbank-azn-server-external")
        prefixes = {"owner": "DEFAULT", "account": "SERVICE", "test": "SERVICE",
                    "credit": "CREDITSCORE", "chat": "CHATBOT"}
        for role, prefix in prefixes.items():
            client = secret.get(f"AZN_AUTHORIZATION_SERVER_{prefix}_CLIENT_ID", "")
            password = secret.get(f"AZN_AUTHORIZATION_SERVER_{prefix}_CLIENT_SECRET", "")
            require(bool(client and password), "oauth-client-configuration-missing")
            self.credentials[role] = (client, password)
        self.owner = self.credentials["owner"][0]
        require(re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", self.owner) is not None, "synthetic-owner-id-invalid")

    def close_forward(self, service: str):
        item = self.forwards.pop(service, None)
        if item:
            process = item[0]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def forward(self, service: str) -> str:
        item = self.forwards.get(service)
        if item and item[0].poll() is None:
            return f"http://127.0.0.1:{item[1]}"
        self.close_forward(service)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(["kubectl", "--context", self.context, "-n", self.namespace,
            "port-forward", "--address=127.0.0.1", "service/" + service, f"{port}:8080"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.forwards[service] = (process, port)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return f"http://127.0.0.1:{port}"
            except OSError:
                time.sleep(0.2)
        self.close_forward(service)
        raise JourneyFailure("service-port-forward-unavailable")

    def send(self, service: str, method: str, path: str, data: bytes | None, headers: dict) -> Response:
        require(service in SERVICES and path.startswith("/") and not path.startswith("//"), "http-target-invalid")
        headers = {**headers, "traceparent": f"00-{hashed(self.run_id)[:32]}-{os.urandom(8).hex()}-01"}
        request = Request(self.forward(service) + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=45)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError, OSError):
            raise JourneyFailure("http-transport-failed") from None
        with contextlib.closing(response):
            body = response.read(256 * 1024 + 1)
            require(len(body) <= 256 * 1024, "http-response-too-large")
            return Response(response.status, body, {k.lower(): v for k, v in response.headers.items()})

    def token(self, role: str) -> str:
        require(role in ROLE_SCOPES, "oauth-role-invalid")
        item = self.tokens.get(role)
        if item and item[1] > time.time() + 30:
            return item[0]
        client, password = self.credentials[role]
        basic = base64.b64encode(f"{client}:{password}".encode()).decode()
        response = self.send("azn-server", "POST", "/oauth2/token",
            urlencode({"grant_type": "client_credentials", "scope": ROLE_SCOPES[role]}).encode(),
            {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
        require(response.status == 200, "oauth-" + role + "-token-request-failed")
        payload = response.json()
        require(isinstance(payload, dict), "oauth-response-invalid")
        token = payload.get("access_token", "")
        require(isinstance(token, str) and len(token) <= 16384 and token.count(".") == 2
                and str(payload.get("token_type", "")).lower() == "bearer", "oauth-response-invalid")
        try:
            encoded = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, UnicodeError):
            raise JourneyFailure("oauth-claims-invalid") from None
        # Decoding is a configuration check, not a signature-verification claim.
        # The subsequent resource-server journeys exercise live token acceptance.
        require(isinstance(claims, dict), "oauth-claims-invalid")
        scopes = set(str(payload.get("scope", "")).split())
        claimed_scopes = claims.get("scope", [])
        if isinstance(claimed_scopes, str):
            claimed_scopes = claimed_scopes.split()
        require(isinstance(claimed_scopes, list) and all(isinstance(s, str) for s in claimed_scopes),
                "oauth-claims-invalid")
        require(scopes == set(claimed_scopes), "oauth-scope-claims-mismatch")
        require(set(ROLE_SCOPES[role].split()) <= scopes, "oauth-" + role + "-scopes-missing")
        if role == "owner":
            require(not scopes & {"cloudbank.internal", "cloudbank.admin"}, "owner-client-is-privileged")
        expiry = claims.get("exp")
        require(type(expiry) in {int, float} and expiry > time.time() + 30
                and claims.get("sub") == client, "oauth-subject-or-expiry-invalid")
        self.tokens[role] = (token, expiry)
        return token

    def authorize(self) -> dict:
        if not self.credentials:
            self.load_credentials()
        self.tokens.clear()
        results = {}
        for role in ROLE_SCOPES:
            self.token(role)
            results[role] = {"issued": True, "required_scopes_granted": True}
        return results

    def authorization_preflight(self) -> dict:
        self.load_credentials()
        results = {}
        for role in ROLE_SCOPES:
            try:
                self.token(role)
                results[role] = {"status": "passed", "required_scopes": ROLE_SCOPES[role]}
            except JourneyFailure as exc:
                results[role] = {"status": "failed", "reason": str(exc), "required_scopes": ROLE_SCOPES[role]}
        return results

    def request(self, service, method, path, role, body=None, headers=None) -> Response:
        headers = dict(headers or {})
        if role is not None:
            headers["Authorization"] = "Bearer " + self.token(role)
        if isinstance(body, str):
            data, headers["Content-Type"] = body.encode(), "text/plain; charset=utf-8"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        else:
            data = b"" if method == "POST" else None
        return self.send(service, method, path, data, headers)

    def recovery_checkpoint(self):
        # Persist restoration intent before scale-down, including immutable
        # deployment UIDs. The recovery command refuses changed deployments.
        payload = {"state_type": "lightyear-cloudbank-journey-recovery", "run_id": self.run_id,
                   "context": self.context, "namespace": self.namespace, "images": self.images,
                   "original_deployments": self.original, "stopped_services": sorted(self.stopped),
                   "probe_name": self.probe_name, "probe_uid": self.probe_uid,
                   "checks_delivery": self.checks_delivery}
        path = self.output / "recovery-state.json"
        temporary = path.with_suffix(".tmp")
        require(bool(self.signing_key and self.signer), "recovery-signing-key-required")
        payload = sign(payload, self.signing_key, self.signer)
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(path)

    def patch_checks_delivery(self, value: dict | None):
        deploy = self.deployment("checks")
        containers = deploy["spec"]["template"]["spec"]["containers"]
        index = next(i for i, container in enumerate(containers) if container["name"] == "checks")
        container = containers[index]
        old = container.get("env", [])
        matches = [i for i, item in enumerate(old) if item.get("name") == "ACCOUNT_JOURNAL_URL"]
        require(len(matches) <= 1, "checks-delivery-configuration-ambiguous")
        base = f"/spec/template/spec/containers/{index}/env"
        patch = [{"op": "test", "path": "/metadata/resourceVersion", "value": deploy["metadata"]["resourceVersion"]}]
        if matches:
            change = {"op": "remove" if value is None else "replace", "path": base + "/" + str(matches[0])}
            if value is not None:
                change["value"] = value
            patch.append(change)
        elif value is not None:
            patch.append({"op": "add", "path": base + "/-" if "env" in container else base,
                          "value": value if "env" in container else [value]})
        # Only the validated nonsecret endpoint/reference enters this patch.
        # Never copy unrelated env entries into argv or a temporary file.
        self.kubectl("patch", "deployment/checks", "--type=json", "--patch", json.dumps(patch))

    def block_checks_delivery(self):
        require(self.checks_delivery is None, "checks-delivery-already-overridden")
        deploy = self.deployment("checks")
        container = next(c for c in deploy["spec"]["template"]["spec"]["containers"] if c["name"] == "checks")
        existing = [item for item in container.get("env", []) if item.get("name") == "ACCOUNT_JOURNAL_URL"]
        require(len(existing) <= 1, "checks-delivery-configuration-ambiguous")
        original = existing[0] if existing else None
        if original and "value" in original:
            url = urlsplit(original["value"])
            require(url.scheme in {"http", "https"} and url.username is None and url.password is None
                    and not url.query and not url.fragment, "checks-delivery-url-contains-sensitive-material")
        blocked = {"name": "ACCOUNT_JOURNAL_URL", "value": "http://192.0.2.1:8080/api/v1/account/journal"}
        self.checks_delivery = {"original": original, "injected": blocked}
        self.recovery_checkpoint()
        previous = set(self.pod_sets.get("checks", set()))
        self.patch_checks_delivery(blocked)
        self.wait_ready("checks", previous)

    def restore_checks_delivery(self):
        if self.checks_delivery is None:
            return
        deploy = self.deployment("checks")
        container = next(c for c in deploy["spec"]["template"]["spec"]["containers"] if c["name"] == "checks")
        current = [item for item in container.get("env", []) if item.get("name") == "ACCOUNT_JOURNAL_URL"]
        original = self.checks_delivery["original"]
        if current != ([] if original is None else [original]):
            require(current == [self.checks_delivery["injected"]], "checks-delivery-changed-by-another-operator")
            previous = set(self.pod_sets.get("checks", set()))
            self.patch_checks_delivery(original)
            if deploy["spec"].get("replicas") == 2:
                self.wait_ready("checks", previous)
        self.checks_delivery = None
        self.recovery_checkpoint()

    def stop(self, service: str):
        self.deployment(service)
        require(service not in self.stopped, "service-already-stopped")
        self.stopped.add(service)
        self.recovery_checkpoint()
        self.close_forward(service)
        self.kubectl("scale", "deployment/" + service, "--current-replicas=2", "--replicas=0")
        if service != "checks":
            deadline = time.monotonic() + 180
            while self.pods(service):
                require(time.monotonic() < deadline, "service-stop-timeout")
                time.sleep(1)

    def _request_start(self, service: str):
        require(service in self.stopped, "restoration-intent-required")
        self.progress("Restoring " + service)
        deploy = self.deployment(service)
        replicas = deploy["spec"].get("replicas")
        require(replicas in {0, 2}, "deployment-replicas-changed-by-another-operator")
        if replicas == 0:
            self.kubectl("scale", "deployment/" + service, "--current-replicas=0", "--replicas=2")
        # Recovery may follow a failed scale command, so only require new pods
        # when the deployment was actually observed at zero replicas.
        return set(self.pod_sets.get(service, set())) if replicas == 0 else None

    def _finish_start(self, service: str, previous):
        self.wait_ready(service, previous)
        self.stopped.remove(service)
        try:
            self.recovery_checkpoint()
        except BaseException:
            self.stopped.add(service)
            raise

    def start(self, service: str):
        self._finish_start(service, self._request_start(service))

    def _restore_grouped(self):
        errors, records = [], {}

        def finish(service, began, status, stage=None):
            records[service].update(status=status,
                finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                elapsed_seconds=round(time.monotonic() - began, 6))
            if stage:
                records[service]["failure_stage"] = stage

        for group in RESTORATION_GROUPS:
            pending = {}
            # Submit every scale-up in this group before observing readiness.
            # A failed request retains its recorded stop intent for recover.
            for service in group:
                if service not in self.stopped:
                    continue
                began = time.monotonic()
                records[service] = {"started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
                try:
                    pending[service] = (self._request_start(service), began)
                except Exception:
                    errors.append("restore-" + service + "-failed")
                    finish(service, began, "failed", "scale-up")
            for service, (previous, began) in pending.items():
                try:
                    self._finish_start(service, previous)
                    finish(service, began, "ready")
                except Exception:
                    errors.append("restore-" + service + "-failed")
                    finish(service, began, "failed", "readiness-or-checkpoint")
            # Cleanup remains best effort after a failure: attempt later groups
            # too, but never report restoration success when a member failed.
        return errors, {"strategy": "dependency-groups",
            "groups": [list(group) for group in RESTORATION_GROUPS],
            "timing_scope": "scale-up request through readiness observation and checkpoint; observation may lag pod readiness",
            "services": records}

    def crash_stopped(self, service: str):
        require(service == "checks" and service in self.stopped, "checks-crash-requires-stop-intent")
        require(self.deployment(service)["spec"].get("replicas") == 0, "checks-must-remain-scaled-down")
        pods = self.pods(service)
        require(bool(pods), "checks-process-exit-preceded-crash-injection")
        for pod in pods:
            name, uid = pod["metadata"]["name"], pod["metadata"]["uid"]
            current = self.get("pod", name)
            require(current["metadata"]["uid"] == uid, "checks-pod-identity-drift")
            self.kubectl("delete", "pod/" + name, "--grace-period=0", "--force", "--wait=false")

    def restart(self, service: str):
        previous = set(self.pod_sets.get(service, set()))
        self.deployment(service)
        self.close_forward(service)
        self.kubectl("rollout", "restart", "deployment/" + service)
        self.wait_ready(service, previous)

    def restart_all(self):
        for service in reversed(SERVICES):
            self.stop(service)
        for service in SERVICES:
            self.start(service)

    def create_probe(self, *, jdbc_url=None):
        require(bool(self.probe_image), "approved-postgresql-probe-image-required")
        jdbc = (jdbc_url if jdbc_url is not None else
                self.secret_json("cloudbank-checks-external").get("SPRING_DATASOURCE_URL", ""))
        require(jdbc.startswith("jdbc:postgresql://"), "postgresql-checks-datasource-required")
        parsed = urlsplit(jdbc.removeprefix("jdbc:"))
        require(parsed.hostname is not None and parsed.username is None and parsed.password is None
                and re.fullmatch(r"/[a-zA-Z0-9_-]+", parsed.path) is not None
                and not parsed.query and not parsed.fragment, "postgresql-datasource-shape-invalid")
        secret_name = "cloudbank-checks-external"
        env = [{"name": "PGHOST", "value": parsed.hostname},
               {"name": "PGPORT", "value": str(parsed.port or 5432)},
               {"name": "PGDATABASE", "value": parsed.path[1:]},
               {"name": "PGCONNECT_TIMEOUT", "value": "10"},
               {"name": "PGOPTIONS", "value": "-c default_transaction_read_only=on -c statement_timeout=10000"}]
        for name, key in (("PGUSER", "SPRING_DATASOURCE_USERNAME"), ("PGPASSWORD", "SPRING_DATASOURCE_PASSWORD")):
            env.append({"name": name, "valueFrom": {"secretKeyRef": {"name": secret_name, "key": key}}})
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": self.probe_name,
            "namespace": self.namespace, "labels": {"app.kubernetes.io/name": "journey-probe",
            "app.kubernetes.io/part-of": "cloudbank", "lightyear.run": self.run_id}}, "spec": {
            "serviceAccountName": "testrunner", "automountServiceAccountToken": False, "restartPolicy": "Never",
            "activeDeadlineSeconds": 7200,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 70, "runAsGroup": 70,
                                "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{"name": "probe", "image": self.probe_image, "command": ["sleep", "7200"], "env": env,
                "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]}},
                "resources": {"requests": {"cpu": "50m", "memory": "32Mi"},
                              "limits": {"cpu": "250m", "memory": "128Mi"}}}]}}
        self.recovery_checkpoint()
        created = json.loads(self.kubectl("create", "-f", "-", "-o", "json", data=json.dumps(pod)))
        self.probe_uid = created["metadata"]["uid"]
        self.recovery_checkpoint()
        self.kubectl("wait", "--for=condition=Ready", "pod/" + self.probe_name, "--timeout=180s", timeout=200)
        version = self.sql("SELECT json_build_object('postgresql', version() LIKE 'PostgreSQL %', 'queue_present', to_regclass('check_messages') IS NOT NULL);")
        require(version == {"postgresql": True, "queue_present": True}, "native-postgresql-queue-probe-failed")

    def sql(self, query: str) -> dict:
        require(self.probe_uid is not None, "postgresql-probe-required")
        pod = self.get("pod", self.probe_name)
        require(pod["metadata"]["uid"] == self.probe_uid, "postgresql-probe-identity-drift")
        raw = self.kubectl("exec", "-i", "pod/" + self.probe_name, "--", "psql", "-X", "-qAt",
                           "--no-password", "--set=ON_ERROR_STOP=1", data=query + "\n")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise JourneyFailure("postgresql-probe-output-invalid") from None
        require(isinstance(result, dict), "postgresql-probe-output-invalid")
        return result

    def queue(self, message_id: str) -> dict:
        require(re.fullmatch(r"ly-[0-9a-f]{48}", message_id) is not None, "queue-message-identity-invalid")
        result = self.sql("SELECT coalesce((SELECT json_build_object('state', state, 'attempts', attempts, "
            "'error_code', last_error_code) "
            "FROM check_messages WHERE message_id = '" + message_id + "'), '{}'::json);")
        require(set(result) in (set(), {"state", "attempts", "error_code"}), "queue-probe-fields-invalid")
        if result:
            require(result["state"] in {"READY", "PROCESSING", "PROCESSED", "DEAD"}
                    and type(result["attempts"]) is int and 0 <= result["attempts"] <= 100,
                    "queue-probe-values-invalid")
            error_code = result["error_code"]
            require(error_code is None or (isinstance(error_code, str)
                    and re.fullmatch(r"[A-Za-z][A-Za-z0-9_$]{0,79}", error_code) is not None),
                    "queue-error-code-invalid")
        return result

    def close(self, *, grouped_restoration=False) -> dict:
        errors = []
        try:
            self.restore_checks_delivery()
        except Exception:
            errors.append("restore-checks-delivery-failed")
        restoration = None
        if grouped_restoration:
            restore_errors, restoration = self._restore_grouped()
            errors.extend(restore_errors)
        else:
            for service in SERVICES:
                if service in self.stopped:
                    try:
                        self.start(service)
                    except Exception:
                        errors.append("restore-" + service + "-failed")
        for service in list(self.forwards):
            try:
                self.close_forward(service)
            except Exception:
                errors.append("close-" + service + "-tunnel-failed")
        try:
            raw = self.kubectl("get", "pod/" + self.probe_name, "--ignore-not-found", "-o", "json")
            if raw.strip():
                current = json.loads(raw)
                require(current["metadata"].get("labels", {}).get("lightyear.run") == self.run_id
                        and (self.probe_uid is None or current["metadata"]["uid"] == self.probe_uid),
                        "probe-cleanup-identity-drift")
                self.kubectl("delete", "pod/" + self.probe_name, "--wait=false")
                self.probe_uid = None
        except Exception:
            errors.append("probe-cleanup-failed")
        self.recovery_checkpoint()
        result = {"status": "failed" if errors or self.stopped else "restored", "errors": errors,
                  "remaining_stopped_services": sorted(self.stopped)}
        if restoration is not None:
            result["application_restoration"] = restoration
        return result
