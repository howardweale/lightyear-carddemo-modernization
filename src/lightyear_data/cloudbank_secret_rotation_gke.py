"""Bounded CreditScore secret rotation and recovery, without persisted secrets.

External Secrets is pinned before addVersion: that API is not idempotent and a
lost response must never be interpreted as proof that no version was created.
Recovery only restores; it never resumes or awards a qualification result.
"""
from __future__ import annotations

import base64
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .cloudbank_journeys import JourneyFailure, require
from .cloudbank_journeys_gke import GkeRuntime, command
from .contracts import canonical_bytes, content_hash, sign, verify_signature


SERVICE = "creditscore"
EXTERNAL = "cloudbank-creditscore"
SECRET = "cloudbank-creditscore-external"
STORE = "cloudbank-gcp-secret-manager"
PEPPER = "CLOUDBANK_CREDITSCORE_SYNTHETIC_PEPPER"
MARKER = "MS67_SYNTHETIC_SECRET_MARKER"
ANNOTATION = "lightyear.ai/ms67-secret-rotation"
LEASE = "ly-ms67-creditscore-secret-rotation"
STATE_TYPE = "lightyear-cloudbank-ms67-secret-rotation-recovery"
OBSERVATION_TYPE = "lightyear-cloudbank-ms67-secret-rotation-observation"
STATE_FILE = "secret-rotation.recovery.json"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hashed(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def verified(value: dict, key: str) -> dict:
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "secret-rotation-signature-invalid")
    return value


def credit_score(pepper: str, subject: str, day: str) -> int:
    digest = hmac.new(pepper.encode("utf-8"), (subject + "\n" + day).encode("utf-8"), hashlib.sha256).digest()
    return 500 + ((int.from_bytes(digest[:4], "big") & 0x7fffffff) % 400)


def rotated_payload(original: dict, subject: str, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    days = [(today + timedelta(days=n)).isoformat() for n in (-1, 0, 1)]
    for _ in range(100):
        pepper = secrets.token_hex(32)
        if all(credit_score(pepper, subject, day) != credit_score(original[PEPPER], subject, day) for day in days):
            return {**original, PEPPER: pepper}
    raise JourneyFailure("secret-rotation-distinct-score-generation-failed")


def check_score(body: dict, pepper: str, subject: str, start: date, end: date,
                prior_pepper: str | None = None) -> None:
    require(isinstance(body, dict) and set(body) == {"Credit Score", "Date", "Provider"},
            "secret-rotation-credit-response-invalid")
    day = body["Date"]
    require(day in {start.isoformat(), end.isoformat()} and body["Provider"] == "synthetic-v1",
            "secret-rotation-credit-date-or-provider-invalid")
    expected = credit_score(pepper, subject, day)
    require(body["Credit Score"] == str(expected), "secret-rotation-pod-secret-not-active")
    if prior_pepper is not None:
        require(expected != credit_score(prior_pepper, subject, day), "secret-rotation-score-collision")


def normalized_external(value: dict) -> dict:
    spec = copy.deepcopy(value["spec"])
    spec["dataFrom"][0]["extract"].pop("version", None)
    return spec


def normalized_deployment(value: dict) -> dict:
    spec = copy.deepcopy(value["spec"])
    metadata = spec["template"].setdefault("metadata", {})
    annotations = metadata.get("annotations", {})
    annotations.pop(ANNOTATION, None)
    if not annotations:
        metadata.pop("annotations", None)
    return spec


class Journal:
    """Signed, atomically replaced local checkpoint, uploaded and read back."""

    def __init__(self, path: Path, uri: str, project: str, key: str, signer: str, invoke=command, generation="0"):
        require(re.fullmatch(r"gs://[a-z0-9][a-z0-9._-]+/[A-Za-z0-9/_.-]+", uri) is not None,
                "secret-rotation-private-evidence-uri-required")
        self.path, self.uri, self.project = path, uri, project
        self.key, self.signer, self.invoke = key, signer, invoke
        self.generation = generation

    def write(self, state: dict) -> dict:
        payload = sign(state, self.key, self.signer)
        raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_suffix(".tmp")
        temporary.touch(mode=0o600, exist_ok=True)
        temporary.write_text(raw, encoding="utf-8")
        temporary.replace(self.path)
        self.invoke(["gcloud", "storage", "cp", str(self.path), self.uri, "--project", self.project,
                     "--if-generation-match=" + self.generation], timeout=180)
        generation = self.invoke(["gcloud", "storage", "objects", "describe", self.uri,
                                  "--project", self.project, "--format=value(generation)"]).strip()
        require(generation.isdigit(), "secret-rotation-checkpoint-generation-invalid")
        readback = self.invoke(["gcloud", "storage", "cat", self.uri + "#" + generation,
                               "--project", self.project], timeout=180)
        require(readback == raw, "secret-rotation-checkpoint-readback-mismatch")
        self.generation = generation
        return payload


class GkeSecretBackend:
    def __init__(self, runtime: GkeRuntime, invoke=command):
        self.r, self.invoke = runtime, invoke
        self.state = None

    def provider(self, *args: str, data=None) -> str:
        return self.invoke(["gcloud", "secrets", *args, "--project", self.r.project, "--quiet"],
                           data=data, timeout=120)

    def parent(self) -> dict:
        value = json.loads(self.provider("describe", SECRET, "--format=json"))
        return {k: value[k] for k in ("name", "createTime")}

    def version(self, number: str) -> dict:
        require(number == "latest" or re.fullmatch(r"[1-9][0-9]*", number) is not None,
                "secret-rotation-version-invalid")
        value = json.loads(self.provider("versions", "describe", number, "--secret", SECRET, "--format=json"))
        require(value["name"].startswith(self.parent()["name"] + "/versions/"),
                "secret-rotation-version-parent-mismatch")
        return value

    def payload(self, number: str) -> dict:
        require(re.fullmatch(r"[1-9][0-9]*", number) is not None, "numeric-secret-version-required")
        value = json.loads(self.provider("versions", "access", number, "--secret", SECRET))
        require(isinstance(value, dict) and set(value) == {PEPPER, MARKER}
                and all(isinstance(v, str) for v in value.values())
                and 32 <= len(value[PEPPER]) <= 4096, "bounded-creditscore-secret-required")
        return value

    def versions(self) -> list[dict]:
        return json.loads(self.provider("versions", "list", SECRET, "--sort-by=~createTime", "--limit=50", "--format=json"))

    def add(self, payload: dict) -> str:
        self.owned(self.state)
        # Secret bytes go only to stdin, never argv, a temporary file or a log.
        value = json.loads(self.provider("versions", "add", SECRET, "--data-file=-", "--format=json",
                                         data=canonical_bytes(payload).decode()))
        require(value["name"].startswith(self.parent()["name"] + "/versions/"),
                "secret-rotation-added-version-parent-mismatch")
        number = value["name"].rsplit("/", 1)[1]
        require(re.fullmatch(r"[1-9][0-9]*", number) is not None, "secret-rotation-added-version-invalid")
        return number

    def disable(self, number: str):
        self.owned(self.state)
        metadata = self.version(number)
        if metadata["state"] == "DISABLED":
            return
        require(metadata["state"] == "ENABLED" and bool(metadata.get("etag")),
                "secret-rotation-version-not-disablable")
        self.provider("versions", "disable", number, "--secret", SECRET, "--etag", metadata["etag"])
        deadline = time.monotonic() + 120
        while self.version(number)["state"] != "DISABLED":
            require(time.monotonic() < deadline, "secret-rotation-disable-not-observed")
            time.sleep(2)

    def secret(self, external_uid: str) -> tuple[dict, dict]:
        value = self.r.get("secret", SECRET)
        require(any(ref.get("uid") == external_uid and ref.get("controller") is True
                    for ref in value["metadata"].get("ownerReferences", [])), "secret-rotation-secret-owner-mismatch")
        payload = {k: base64.b64decode(v, validate=True).decode("utf-8") for k, v in value.get("data", {}).items()}
        return value, payload

    def preflight(self) -> tuple[dict, dict]:
        environment = self.r.environment()
        for service in self.r.images:
            self.r.service_ready(service)
            external = self.r.get("externalsecret", "cloudbank-" + service)
            require(self.ready(external), "secret-rotation-external-secret-not-ready")
        external = self.r.get("externalsecret", EXTERNAL)
        spec = external["spec"]
        require(spec.get("secretStoreRef") == {"kind": "SecretStore", "name": STORE}
                and spec.get("target", {}).get("name") == SECRET
                and spec.get("target", {}).get("creationPolicy") == "Owner"
                and not spec.get("target", {}).get("template") and not spec.get("data")
                and spec.get("refreshInterval") == "1m"
                and spec.get("refreshPolicy", "Periodic") == "Periodic"
                and len(spec.get("dataFrom", [])) == 1
                and set(spec["dataFrom"][0]) == {"extract"}, "secret-rotation-external-mapping-invalid")
        extract = spec["dataFrom"][0]["extract"]
        require(extract.get("key") == SECRET and extract.get("version", "latest") == "latest"
                and not extract.get("property") and extract.get("decodingStrategy", "None") == "None"
                and extract.get("conversionStrategy", "Default") == "Default",
                "secret-rotation-extract-mapping-invalid")
        store = self.r.get("secretstore", STORE)
        require(store["spec"]["provider"]["gcpsm"]["projectID"] == self.r.project and self.ready(store),
                "secret-rotation-provider-project-invalid")
        deploy = self.r.deployment(SERVICE)
        template = deploy["spec"]["template"]
        container = next(c for c in template["spec"]["containers"] if c["name"] == SERVICE)
        require(ANNOTATION not in template.get("metadata", {}).get("annotations", {})
                and deploy["spec"]["strategy"] == {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}}
                and container.get("envFrom") == [{"configMapRef": {"name": "cloudbank-runtime"}}, {"secretRef": {"name": SECRET}}]
                and not any(row.get("name") in {PEPPER, "CREDITSCORE_SYNTHETIC_PEPPER", "SPRING_APPLICATION_JSON"}
                            for row in container.get("env", [])), "secret-rotation-deployment-mapping-invalid")
        config = self.r.get("configmap", "cloudbank-runtime")
        require(not {PEPPER, "CREDITSCORE_SYNTHETIC_PEPPER", "SPRING_APPLICATION_JSON"} & set(config.get("data", {})),
                "secret-rotation-configmap-overrides-secret")
        parent = self.parent()
        version = self.version("latest")
        number = version["name"].rsplit("/", 1)[1]
        require(version["state"] == "ENABLED", "secret-rotation-original-version-not-enabled")
        original = self.payload(number)
        secret, live = self.secret(external["metadata"]["uid"])
        require(live == original, "secret-rotation-original-sync-mismatch")
        oauth = self.r.secret_json("cloudbank-azn-server-external")
        client = oauth.get("AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID", "")
        password = oauth.get("AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SECRET", "")
        require(bool(client and password), "secret-rotation-credit-oauth-configuration-missing")
        self.r.credentials["credit"] = (client, password)
        return {
            "environment": environment, "parent": parent, "original_version": number,
            "original_payload_sha256": hashed(original), "subject_sha256": hashed(client),
            "external_uid": external["metadata"]["uid"], "external_spec_sha256": hashed(normalized_external(external)),
            "original_version_field": {"version": "latest"} if "version" in extract else {},
            "store_uid": store["metadata"]["uid"], "store_spec_sha256": hashed(store["spec"]),
            "deployment_uid": deploy["metadata"]["uid"], "deployment_spec_sha256": hashed(normalized_deployment(deploy)),
            "config_uid": config["metadata"]["uid"], "config_sha256": hashed(config.get("data", {})),
            "secret_uid": secret["metadata"]["uid"],
        }, original

    def load_credit_credentials(self, state: dict):
        oauth = self.r.secret_json("cloudbank-azn-server-external")
        client = oauth.get("AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID", "")
        password = oauth.get("AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SECRET", "")
        require(bool(client and password) and hashed(client) == state["baseline"]["subject_sha256"],
                "secret-rotation-credit-subject-drift")
        self.r.credentials["credit"] = (client, password)

    @staticmethod
    def ready(value: dict) -> bool:
        return any(c.get("type") == "Ready" and c.get("status") == "True" for c in value.get("status", {}).get("conditions", []))

    def guard(self, state: dict):
        self.state = state
        b = state["baseline"]
        require(self.r.environment() == b["environment"] and self.parent() == b["parent"],
                "secret-rotation-environment-or-provider-drift")
        external = self.r.get("externalsecret", EXTERNAL)
        deploy = self.r.deployment(SERVICE)
        store = self.r.get("secretstore", STORE)
        config = self.r.get("configmap", "cloudbank-runtime")
        secret, _ = self.secret(b["external_uid"])
        require(external["metadata"]["uid"] == b["external_uid"]
                and hashed(normalized_external(external)) == b["external_spec_sha256"]
                and deploy["metadata"]["uid"] == b["deployment_uid"]
                and hashed(normalized_deployment(deploy)) == b["deployment_spec_sha256"]
                and store["metadata"]["uid"] == b["store_uid"] and hashed(store["spec"]) == b["store_spec_sha256"]
                and config["metadata"]["uid"] == b["config_uid"] and hashed(config.get("data", {})) == b["config_sha256"]
                and secret["metadata"]["uid"] == b["secret_uid"], "secret-rotation-live-identity-or-config-drift")
        allowed = {b["original_version"], "latest", None, *state["versions"].values()}
        require(external["spec"]["dataFrom"][0]["extract"].get("version") in allowed,
                "secret-rotation-version-pin-changed-by-another-operator")
        require(deploy["spec"]["template"].get("metadata", {}).get("annotations", {}).get(ANNOTATION)
                in {None, state["run_id"] + ":rotated", state["run_id"] + ":restored"},
                "secret-rotation-rollout-changed-by-another-operator")

    def patch(self, kind: str, value: dict, changes: list):
        if kind != "lease":
            self.owned(self.state)
            b = self.state["baseline"]
            if kind == "externalsecret":
                require(value["metadata"]["uid"] == b["external_uid"]
                        and hashed(normalized_external(value)) == b["external_spec_sha256"]
                        and value["spec"]["dataFrom"][0]["extract"].get("version")
                        in {None, "latest", b["original_version"], *self.state["versions"].values()},
                        "secret-rotation-patch-external-drift")
            elif kind == "deployment":
                require(value["metadata"]["uid"] == b["deployment_uid"]
                        and hashed(normalized_deployment(value)) == b["deployment_spec_sha256"]
                        and value["spec"]["template"].get("metadata", {}).get("annotations", {}).get(ANNOTATION)
                        in {None, self.state["run_id"] + ":rotated", self.state["run_id"] + ":restored"},
                        "secret-rotation-patch-deployment-drift")
        patch = [{"op": "test", "path": "/metadata/uid", "value": value["metadata"]["uid"]},
                 {"op": "test", "path": "/metadata/resourceVersion", "value": value["metadata"]["resourceVersion"]}, *changes]
        # Only nonsecret IDs, resource versions and our annotation enter argv.
        self.r.kubectl("patch", kind + "/" + value["metadata"]["name"], "--type=json", "--patch", json.dumps(patch))

    def pin(self, number: str | None):
        external = self.r.get("externalsecret", EXTERNAL)
        extract = external["spec"]["dataFrom"][0]["extract"]
        path = "/spec/dataFrom/0/extract/version"
        if number is None:
            changes = [{"op": "remove", "path": path}] if "version" in extract else []
        else:
            changes = [] if extract.get("version") == number else [{"op": "add", "path": path, "value": number}]
        if changes:
            self.patch("externalsecret", external, changes)

    def sync(self, state: dict, payload: dict):
        deadline = time.monotonic() + 180
        while True:
            self.guard(state)
            _, actual = self.secret(state["baseline"]["external_uid"])
            if actual == payload and self.ready(self.r.get("externalsecret", EXTERNAL)):
                return
            require(time.monotonic() < deadline, "secret-rotation-sync-timeout")
            time.sleep(3)

    def rollout(self, marker: str | None):
        deploy = self.r.deployment(SERVICE)
        metadata = deploy["spec"]["template"].get("metadata", {})
        annotations = metadata.get("annotations", {})
        path = "/spec/template/metadata/annotations/" + ANNOTATION.replace("/", "~1")
        changes = []
        if marker is None and ANNOTATION in annotations:
            changes = [{"op": "remove", "path": path}]
            if len(annotations) == 1:
                changes = [{"op": "remove", "path": "/spec/template/metadata/annotations"}]
        elif marker is not None and annotations.get(ANNOTATION) != marker:
            changes = [{"op": "add", "path": path, "value": marker}] if "annotations" in metadata else [
                {"op": "add", "path": "/spec/template/metadata/annotations", "value": {ANNOTATION: marker}}]
        if changes:
            self.patch("deployment", deploy, changes)
        self.r.wait_ready(SERVICE)

    def observe(self, state: dict, payload: dict, prior: dict | None = None) -> dict:
        self.guard(state)
        self.r.service_ready(SERVICE)
        pods = self.r.pods(SERVICE)
        subject = self.r.credentials["credit"][0]
        require(hashed(subject) == state["baseline"]["subject_sha256"], "secret-rotation-credit-subject-drift")
        observed = []
        for pod in pods:
            # Forward explicitly to each owned pod: a Service forward selects
            # only one replica and cannot establish two-replica propagation.
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = subprocess.Popen(["kubectl", "--context", self.r.context, "-n", self.r.namespace,
                "port-forward", "--address=127.0.0.1", "pod/" + pod["metadata"]["name"], f"{port}:8080"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.r.close_forward(SERVICE)
            self.r.forwards[SERVICE] = (process, port)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=1):
                            break
                    except OSError:
                        require(process.poll() is None and time.monotonic() < deadline, "secret-rotation-pod-forward-unavailable")
                        time.sleep(0.2)
                start = datetime.now(timezone.utc).date()
                request = Request(f"http://127.0.0.1:{port}/api/v1/creditscore", headers={
                    "Authorization": "Bearer " + self.r.token("credit"),
                    "traceparent": f"00-{hashed(state['run_id'])[:32]}-{secrets.token_hex(8)}-01"})
                try:
                    # GkeRuntime.send retries a dead forward via a Service;
                    # that fallback could select a different replica here.
                    with self.r.opener.open(request, timeout=45) as response:
                        require(response.status == 200, "secret-rotation-credit-request-failed")
                        raw = response.read(16385)
                        require(len(raw) <= 16384 and process.poll() is None, "secret-rotation-pod-response-invalid")
                        body = json.loads(raw)
                except (HTTPError, URLError, OSError, ValueError):
                    raise JourneyFailure("secret-rotation-credit-request-failed") from None
                check_score(body, payload[PEPPER], subject, start, datetime.now(timezone.utc).date(),
                            prior[PEPPER] if prior else None)
                current = self.r.get("pod", pod["metadata"]["name"])
                require(current["metadata"]["uid"] == pod["metadata"]["uid"] and not current["metadata"].get("deletionTimestamp"),
                        "secret-rotation-observed-pod-replaced")
                observed.append(hashed(pod["metadata"]["uid"]))
            finally:
                self.r.close_forward(SERVICE)
        self.r.service_ready(SERVICE)
        require(set(observed) == {hashed(p["metadata"]["uid"]) for p in self.r.pods(SERVICE)} and len(observed) == 2,
                "secret-rotation-pod-set-changed")
        return {"observed_at": utc(), "pod_uid_sha256": sorted(observed), "verified_replicas": 2,
                "authenticated_contract_matches": True, "different_from_prior": prior is not None}

    def lease(self) -> dict | None:
        raw = self.r.kubectl("get", "lease", LEASE, "--ignore-not-found", "-o", "json")
        return json.loads(raw) if raw.strip() else None

    def acquire(self, state: dict):
        lease = self.lease()
        if lease is None:
            self.r.kubectl("create", "-f", "-", data=json.dumps({"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                "metadata": {"name": LEASE, "namespace": self.r.namespace,
                    "labels": {"app.kubernetes.io/managed-by": "lightyear-secret-rotation"},
                    "annotations": {"lightyear.ai/recovery-state": state["recovery_uri"],
                                    "lightyear.ai/executor": state["executor_id"]}},
                "spec": {"holderIdentity": state["run_id"]}}))
        else:
            require(lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == "lightyear-secret-rotation"
                    and not lease.get("spec", {}).get("holderIdentity"), "secret-rotation-lock-held-recovery-required")
            self.patch("lease", lease, [
                {"op": "add", "path": "/spec/holderIdentity", "value": state["run_id"]},
                {"op": "add", "path": "/metadata/annotations/lightyear.ai~1executor", "value": state["executor_id"]},
                {"op": "add", "path": "/metadata/annotations/lightyear.ai~1recovery-state", "value": state["recovery_uri"]}])
        return self.lease()["metadata"]["uid"]

    def owned(self, state: dict):
        lease = self.lease()
        require(lease is not None and lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == "lightyear-secret-rotation"
                and lease.get("spec", {}).get("holderIdentity") == state["run_id"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/executor") == state["executor_id"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/recovery-state") == state["recovery_uri"]
                and (state.get("lease_uid") is None or state["lease_uid"] == lease["metadata"]["uid"]),
                "secret-rotation-lock-ownership-mismatch")
        return lease

    def takeover(self, state: dict):
        lease = self.lease()
        require(lease is not None and lease["metadata"]["uid"] == state["lease_uid"]
                and lease["metadata"].get("labels", {}).get("app.kubernetes.io/managed-by") == "lightyear-secret-rotation"
                and lease.get("spec", {}).get("holderIdentity") == state["run_id"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/recovery-state") == state["recovery_uri"]
                and lease["metadata"].get("annotations", {}).get("lightyear.ai/executor")
                in {state["executor_id"], state["prior_executor_id"]}, "secret-rotation-recovery-lock-mismatch")
        self.patch("lease", lease, [{"op": "add", "path": "/metadata/annotations/lightyear.ai~1executor", "value": state["executor_id"]}])

    def release(self, state: dict):
        lease = self.owned(state)
        self.patch("lease", lease, [{"op": "add", "path": "/spec/holderIdentity", "value": ""}])


class SecretRotation:
    def __init__(self, backend: GkeSecretBackend, journal: Journal, state: dict):
        self.b, self.journal, self.state = backend, journal, state

    def save(self, phase: str):
        self.state.update(phase=phase, updated_at=utc())
        messages = {
            "before-lock": "Acquiring the CreditScore rotation lock",
            "before-add-rotated": "Adding the new synthetic scoring secret under the original version pin",
            "before-pin-rotated": "Propagating the recorded new version through External Secrets",
            "before-rotation-rollout": "Rolling CreditScore and checking each new replica",
            "rotated-value-proved-on-both-replicas": "New scoring secret verified on both replicas",
            "restore-started": "Restoring the original scoring values and version policy",
            "before-disable-temporary-version": "Retiring the temporary version after verified restoration",
            "lock-released": "CreditScore restored and rotation lock released",
        }
        if phase in messages:
            getattr(self.b.r, "progress", lambda _: None)(messages[phase])
        self.journal.write(self.state)

    def before(self, phase: str):
        self.b.owned(self.state)
        self.b.guard(self.state)
        self.save(phase)

    def original(self) -> dict:
        baseline = self.state["baseline"]
        require(self.b.version(baseline["original_version"])["state"] == "ENABLED",
                "secret-rotation-original-version-unavailable")
        payload = self.b.payload(baseline["original_version"])
        require(hashed(payload) == baseline["original_payload_sha256"], "secret-rotation-original-payload-drift")
        return payload

    def head(self) -> str:
        expected = self.state["versions"].get("restored") or self.state["versions"].get("rotated") or self.state["baseline"]["original_version"]
        known = {self.state["baseline"]["original_version"], *self.state["versions"].values()}
        deadline = time.monotonic() + 120
        while True:
            number = self.b.version("latest")["name"].rsplit("/", 1)[1]
            if number == expected:
                return number
            # Numeric reads prove payload identity. Allow a bounded period for
            # the latest alias to catch up, but never accept an unknown head.
            require(number in known and int(number) < int(expected), "secret-rotation-provider-head-changed")
            require(time.monotonic() < deadline, "secret-rotation-latest-alias-not-converged")
            time.sleep(2)

    def reconcile_pending(self):
        pending = self.state.get("pending_add")
        if not pending:
            return
        self.b.owned(self.state)
        self.b.guard(self.state)
        # A positively identified version resolves a lost addVersion response.
        # An empty/eventually-consistent list does not authorize a retry.
        candidates = []
        for row in self.b.versions():
            number = row["name"].rsplit("/", 1)[1]
            require(row["name"].startswith(self.state["baseline"]["parent"]["name"] + "/versions/"),
                    "secret-rotation-listed-version-parent-mismatch")
            if int(number) > int(pending["after_version"]):
                require(row["state"] == "ENABLED" and hashed(self.b.payload(number)) == pending["payload_sha256"],
                        "secret-rotation-unrecognized-provider-version")
                candidates.append(number)
        require(len(candidates) == 1, "secret-rotation-add-outcome-uncertain")
        self.state["versions"][pending["purpose"]] = candidates[0]
        self.state["version_payloads"][pending["purpose"]] = pending["payload_sha256"]
        self.state["pending_add"] = None
        self.save("add-response-reconciled")

    def add(self, purpose: str, payload: dict) -> str:
        require(purpose in {"rotated", "restored"} and not self.state.get("pending_add"), "secret-rotation-add-intent-invalid")
        if purpose in self.state["versions"]:
            number = self.state["versions"][purpose]
            require(hashed(self.b.payload(number)) == hashed(payload), "secret-rotation-recorded-version-payload-mismatch")
            return number
        head = self.head()
        self.state["pending_add"] = {"purpose": purpose, "after_version": head, "payload_sha256": hashed(payload)}
        self.before("before-add-" + purpose)
        number = self.b.add(payload)
        require(int(number) > int(head) and hashed(self.b.payload(number)) == hashed(payload),
                "secret-rotation-added-version-mismatch")
        self.state["versions"][purpose] = number
        self.state["version_payloads"][purpose] = hashed(payload)
        self.state["pending_add"] = None
        self.save("added-" + purpose)
        self.head()
        return number

    def restore(self) -> dict:
        self.before("restore-started")
        original = self.original()
        # Restore runtime behavior even when an add acknowledgement was lost.
        # Keep the numeric pin and lock if provider reconciliation is uncertain.
        self.before("before-pin-original")
        self.b.pin(self.state["baseline"]["original_version"])
        self.b.sync(self.state, original)
        self.before("before-restoration-rollout")
        self.b.rollout(self.state["run_id"] + ":restored")
        self.state["observations"]["restored_pinned"] = self.b.observe(self.state, original)
        self.save("original-behavior-restored")
        self.reconcile_pending()
        self.head()
        if self.state["versions"]:
            number = self.add("restored", original)
            self.before("before-pin-restored")
            self.b.pin(number)
            self.b.sync(self.state, original)
        # Releasing latest is safe only after its current head was identified.
        self.head()
        self.before("before-original-version-policy")
        self.b.pin(self.state["baseline"]["original_version_field"].get("version"))
        self.b.sync(self.state, original)
        self.head()
        self.before("before-original-pod-template")
        self.b.rollout(None)
        self.state["observations"]["restored"] = self.b.observe(self.state, original)
        number = self.state["versions"].get("rotated")
        if number:
            require(number not in {self.state["baseline"]["original_version"], self.state["versions"].get("restored")},
                    "secret-rotation-disable-original-prohibited")
            metadata = self.b.version(number)
            require(metadata["state"] in {"ENABLED", "DISABLED"}, "secret-rotation-owned-version-state-invalid")
            if metadata["state"] == "ENABLED":
                require(hashed(self.b.payload(number)) == self.state["version_payloads"]["rotated"],
                        "secret-rotation-disable-payload-mismatch")
            self.before("before-disable-temporary-version")
            self.b.disable(number)
        self.head()
        self.b.sync(self.state, original)
        self.state["cleanup_complete"] = True
        self.save("restored")
        self.b.release(self.state)
        self.save("lock-released")
        return {"status": "restored", "temporary_version_disabled": bool(number), "original_values_restored": True,
                "preexisting_versions_unchanged": True, "errors": []}

    def run(self, original: dict) -> dict:
        self.save("before-lock")
        self.state["lease_uid"] = self.b.acquire(self.state)
        self.save("lock-acquired")
        self.before("before-baseline-probe")
        self.state["observations"]["baseline"] = self.b.observe(self.state, original)
        self.before("before-pin-original")
        self.head()
        self.b.pin(self.state["baseline"]["original_version"])
        self.b.sync(self.state, original)
        payload = rotated_payload(original, self.b.r.credentials["credit"][0])
        number = self.add("rotated", payload)
        self.before("before-pin-rotated")
        self.b.pin(number)
        self.b.sync(self.state, payload)
        self.before("before-rotation-rollout")
        self.b.rollout(self.state["run_id"] + ":rotated")
        observed = self.b.observe(self.state, payload, original)
        require(set(observed["pod_uid_sha256"]).isdisjoint(self.state["observations"]["baseline"]["pod_uid_sha256"]),
                "secret-rotation-fresh-replicas-required")
        self.state["observations"]["rotated"] = observed
        self.save("rotated-value-proved-on-both-replicas")
        cleanup = self.restore()
        return self.observation("passed-secret-rotation-and-restoration", cleanup)

    def observation(self, status: str, cleanup: dict) -> dict:
        return {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "status": status,
            "run_id": self.state["run_id"], "bindings": self.state["bindings"],
            "environment": self.state["baseline"]["environment"], "service": SERVICE,
            "versions": self.state["versions"], "observations": self.state["observations"], "recovery": cleanup,
            "credentials_persisted": False, "raw_output_persisted": False, "production_environment": False,
            "ms67_complete": False, "production_ready": False}
