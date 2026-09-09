"""Bounded verification of the eight approved MS67 container images.

Cosign verifies cryptography; these checks bind its verified claims to the exact
approved image and build source. Trivy reports must include OS and Java package
coverage. Empty output, suppressed findings and a failed scanner cannot pass.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .cloudbank_journeys import JourneyFailure, SERVICES, require
from .cloudbank_journeys_gke import command
from .cloudbank_secret_rotation_gke import Journal
from .contracts import content_hash, sign, verify_signature


OBSERVATION_TYPE = "lightyear-cloudbank-ms67-image-security-observation"
OBSERVATION_FILE = "image-security.observation.json"
PASS = "passed-eight-image-security"
SOURCE_URI = "git+https://github.com/howardweale/lightyear-carddemo-modernization"
HEX64 = r"[0-9a-f]{64}"
MAX_OUTPUT = 32 * 1024 * 1024
HELPER = "lightyear-ms67"


class CheckpointFailure(JourneyFailure):
    """The intended evidence object has not been independently confirmed."""


def save_observation(path, state, key, signer):
    payload = sign(state, key, signer)
    temporary = path.with_suffix(".tmp")
    temporary.touch(mode=0o600, exist_ok=True)
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return payload


class ImageJournal(Journal):
    """Retry one image checkpoint without overwriting an unrecognized generation.

    A lost upload response is resolved by reading the exact observed generation.
    Only identical signed bytes acknowledge that upload. Other executors' data
    must never advance our generation precondition.
    """

    def write(self, state):
        payload = save_observation(self.path, state, self.key, self.signer)
        raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        uploaded, stage = False, "upload"
        for _ in range(3):
            if not uploaded:
                try:
                    self.invoke(["gcloud", "storage", "cp", str(self.path), self.uri, "--project", self.project,
                                 "--if-generation-match=" + self.generation], timeout=90)
                    uploaded = True
                except JourneyFailure:
                    # The upload may have committed despite a lost response.
                    pass
            try:
                stage = "generation"
                generation = self.invoke(["gcloud", "storage", "objects", "describe", self.uri,
                                          "--project", self.project, "--format=value(generation)"], timeout=60).strip()
                require(re.fullmatch(r"[1-9][0-9]*", generation), "image-security-checkpoint-generation-invalid")
                stage = "readback"
                readback = self.invoke(["gcloud", "storage", "cat", self.uri + "#" + generation,
                                       "--project", self.project], timeout=90)
            except JourneyFailure:
                continue
            if readback == raw:
                self.generation = generation
                return payload
            if generation != self.generation or uploaded:
                raise CheckpointFailure("image-security-checkpoint-conflict")
            stage = "upload"
        raise CheckpointFailure("image-security-checkpoint-" + stage + "-unconfirmed")


def credential_helper():
    """Docker's get-only protocol; the short-lived token exists only in memory."""
    host = sys.stdin.readline(1025).strip()
    expected = os.environ.get("MS67_REGISTRY_HOST", "")
    token = os.environ.get("MS67_REGISTRY_ACCESS_TOKEN", "")
    if (sys.argv[1:] != ["get"] or not expected or not token
            or host not in {expected, "https://" + expected}):
        return 1
    print(json.dumps({"Username": "oauth2accesstoken", "Secret": token}))
    return 0


def install_credential_helper(workspace, host):
    # distlib creates a native .exe launcher on Windows. Go-based registry
    # clients cannot directly launch the SDK's gcloud.cmd entry point there.
    try:
        from distlib.scripts import ScriptMaker
    except ImportError:
        raise JourneyFailure("image-security-distlib-required") from None
    directory = workspace / "helpers"
    directory.mkdir()
    maker = ScriptMaker(None, str(directory))
    maker.executable, maker.variants, maker.set_mode = sys.executable, {""}, True
    maker.make("docker-credential-" + HELPER + " = lightyear_data.cloudbank_image_security:credential_helper")
    (workspace / "docker/config.json").write_text(json.dumps({"credHelpers": {host: HELPER}}), encoding="utf-8")


def stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()


def instant(value):
    require(isinstance(value, str), "image-security-timestamp-invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise JourneyFailure("image-security-timestamp-invalid") from None
    require(result.tzinfo is not None, "image-security-timestamp-invalid")
    return result


def documents(raw):
    """Cosign emits arrays for signatures and JSON streams for attestations."""
    require(isinstance(raw, str) and 0 < len(raw) <= MAX_OUTPUT, "image-security-json-output-required")
    decoder, rows = json.JSONDecoder(), []
    remaining = raw.strip()
    try:
        while remaining:
            value, offset = decoder.raw_decode(remaining)
            rows.extend(value if isinstance(value, list) else [value])
            remaining = remaining[offset:].strip()
    except (ValueError, UnicodeError):
        raise JourneyFailure("image-security-json-output-invalid") from None
    require(0 < len(rows) <= 100 and all(isinstance(x, dict) for x in rows),
            "image-security-json-records-invalid")
    return rows


def signature_summary(raw, image):
    rows = documents(raw)
    repository, digest = image.split("@")
    for row in rows:
        critical = row.get("critical", {})
        require(critical.get("image", {}).get("docker-manifest-digest") == digest
                and critical.get("identity", {}).get("docker-reference") in {repository, image},
                "image-security-signature-image-mismatch")
    return {"verified": True, "count": len(rows), "output_sha256": sha(raw)}


def provenance_summary(raw, image, service, source_commit):
    matches = []
    repository, digest = image.split("@sha256:")
    for envelope in documents(raw):
        require(envelope.get("payloadType") == "application/vnd.in-toto+json"
                and isinstance(envelope.get("payload"), str), "image-security-provenance-envelope-invalid")
        try:
            statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
        except (ValueError, UnicodeError):
            raise JourneyFailure("image-security-provenance-payload-invalid") from None
        require(isinstance(statement, dict), "image-security-provenance-payload-invalid")
        subjects = statement.get("subject")
        require(statement.get("_type") in {"https://in-toto.io/Statement/v0.1", "https://in-toto.io/Statement/v1"}
                and statement.get("predicateType") == "https://slsa.dev/provenance/v0.2"
                and isinstance(subjects, list) and len(subjects) == 1
                and subjects[0].get("name") in {repository, image}
                and subjects[0].get("digest") == {"sha256": digest},
                "image-security-provenance-subject-mismatch")
        predicate = statement.get("predicate", {})
        materials = predicate.get("materials", [])
        require(predicate.get("builder", {}).get("id") == "lightyear-ms67-operator"
                and predicate.get("buildType") == "https://lightyear.ai/cloudbank/ms67"
                and predicate.get("invocation", {}).get("parameters", {}).get("service") == service
                and isinstance(materials, list)
                and [x for x in materials if x.get("uri") == SOURCE_URI] == [
                    {"uri": SOURCE_URI, "digest": {"sha1": source_commit}}]
                and [x for x in materials if x.get("uri") == image] == [
                    {"uri": image, "digest": {"sha256": digest}}],
                "image-security-provenance-build-mismatch")
        matches.append(sha(json.dumps(statement, sort_keys=True, separators=(",", ":"))))
    return {"verified": True, "count": len(matches), "output_sha256": sha(raw),
            "statement_sha256": sorted(set(matches)), "source_commit": source_commit}


def scan_summary(raw, image):
    rows = documents(raw)
    require(len(rows) == 1, "image-security-one-scan-report-required")
    report = rows[0]
    metadata = report.get("Metadata", {})
    require(report.get("SchemaVersion") == 2 and report.get("ArtifactName") == image
            and report.get("ArtifactType") == "container_image"
            and image in metadata.get("RepoDigests", []), "image-security-scan-image-mismatch")
    config = metadata.get("ImageConfig", {})
    require(config.get("architecture") == "amd64" and config.get("os") == "linux",
            "image-security-scan-platform-mismatch")
    results = report.get("Results")
    require(isinstance(results, list) and results and all(isinstance(r, dict) for r in results),
            "image-security-scan-results-required")
    coverage = {"os_packages": 0, "java_packages": 0}
    counts = {level: 0 for level in ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")}
    findings = set()
    for result in results:
        packages = result.get("Packages") or []
        require(isinstance(packages, list) and all(isinstance(p, dict) and p.get("Name") and p.get("Version")
                                                  for p in packages), "image-security-scan-package-list-invalid")
        if result.get("Class") == "os-pkgs":
            coverage["os_packages"] += len(packages)
        if result.get("Class") == "lang-pkgs" and result.get("Type") == "jar":
            coverage["java_packages"] += len(packages)
        require(not result.get("ModifiedFindings") and not result.get("ExperimentalModifiedFindings"),
                "image-security-suppressed-findings-not-allowed")
        vulnerabilities = result.get("Vulnerabilities") or []
        require(isinstance(vulnerabilities, list), "image-security-scan-findings-invalid")
        for finding in vulnerabilities:
            require(isinstance(finding, dict) and finding.get("Severity") in counts,
                    "image-security-scan-severity-invalid")
            level = finding["Severity"]
            counts[level] += 1
            if level in {"HIGH", "CRITICAL"}:
                identifier = finding.get("VulnerabilityID", "")
                require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", identifier),
                        "image-security-finding-id-invalid")
                findings.add((level, identifier))
    require(all(count > 0 for count in coverage.values()), "image-security-os-and-java-coverage-required")
    return {"scan_sha256": sha(raw), "critical": counts["CRITICAL"], "high": counts["HIGH"],
            "severity_counts": counts, "coverage": coverage,
            "finding_ids": [{"severity": level, "id": identifier} for level, identifier in sorted(findings)[:100]],
            "finding_ids_complete": len(findings) <= 100}


def database_summary(cache, scan_started):
    result = {}
    for name, version in (("db", 2), ("java-db", 1)):
        path = Path(cache) / name / "metadata.json"
        require(path.is_file() and path.stat().st_size < 16384, "image-security-database-metadata-required")
        raw = path.read_bytes()
        value = json.loads(raw)
        require(value.get("Version") == version, "image-security-database-version-invalid")
        updated, next_update = instant(value.get("UpdatedAt")), instant(value.get("NextUpdate"))
        require(updated <= instant(scan_started) < next_update, "image-security-database-not-current")
        result[name] = {"version": version, "updated_at": value["UpdatedAt"],
                        "next_update": value["NextUpdate"], "metadata_sha256": sha(raw)}
    return result


def child_environment(workspace, token=None, host=None):
    # Ignore operator scanner overrides and Docker config without rewriting it.
    result = {k: v for k, v in os.environ.items()
              if not k.upper().startswith(("TRIVY_", "COSIGN_", "LIGHTYEAR_", "MS67_REGISTRY_"))
              and k.upper() not in {"DOCKER_CONFIG", "DOCKER_AUTH_CONFIG", "REGISTRY_AUTH_FILE"}}
    result["DOCKER_CONFIG"] = str(workspace / "docker")
    result["PATH"] = str(workspace / "helpers") + os.pathsep + result.get("PATH", "")
    result["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    if token:
        # Global TRIVY_USERNAME/PASSWORD also apply to public database registries.
        # Both clients instead use the helper scoped to this Artifact Registry host.
        result.update(MS67_REGISTRY_ACCESS_TOKEN=token, MS67_REGISTRY_HOST=host or "")
    return result


def execute_tool(argv, *, workspace, env, timeout=300):
    try:
        completed = subprocess.run(argv, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise JourneyFailure("image-security-tool-unavailable-or-timed-out") from None
    require(completed.returncode == 0, f"image-security-tool-failed-{Path(argv[0]).stem}-exit-{completed.returncode}")
    require(0 < len(completed.stdout) <= MAX_OUTPUT, "image-security-tool-output-invalid")
    try:
        return completed.stdout.decode("utf-8")
    except UnicodeError:
        raise JourneyFailure("image-security-tool-output-invalid") from None


def signing_public_key(project, region, *, invoke=command):
    number = invoke(["gcloud", "projects", "describe", project,
                     "--format=value(projectNumber)"]).strip()
    require(number.isdigit(), "image-security-project-number-required")
    versions = json.loads(invoke(["gcloud", "kms", "keys", "versions", "list", "--key", "image-signing",
        "--keyring", "cloudbank-ms67", "--location", region, "--project", project,
        "--format=json(name,state,algorithm)"]))
    require(isinstance(versions, list) and len(versions) <= 100, "image-security-key-version-list-invalid")
    enabled = [v for v in versions if v.get("state") == "ENABLED"]
    require(len(enabled) == 1, "image-security-single-enabled-signing-version-required")
    version = enabled[0]
    parent = f"locations/{region}/keyRings/cloudbank-ms67/cryptoKeys/image-signing/cryptoKeyVersions/"
    require(any(re.fullmatch(re.escape(f"projects/{p}/" + parent) + r"[1-9][0-9]*", version.get("name", ""))
                for p in (project, number))
            and "SIGN" in version.get("algorithm", ""), "image-security-key-identity-invalid")
    raw = invoke(["gcloud", "kms", "keys", "versions", "get-public-key", version["name"].split("/")[-1],
                  "--key", "image-signing", "--keyring", "cloudbank-ms67", "--location", region,
                  "--project", project, "--public-key-format=pem"])
    require(raw.startswith("-----BEGIN PUBLIC KEY-----") and "-----END PUBLIC KEY-----" in raw,
            "image-security-public-key-invalid")
    return raw, {"version": version["name"], "algorithm": version["algorithm"],
                 "project_number": number, "public_key_sha256": sha(raw)}


class ImageScanner:
    def __init__(self, project, region, workspace, *, invoke=command, run=execute_tool):
        self.project, self.region, self.workspace = project, region, Path(workspace)
        self.invoke, self.run = invoke, run
        self.cache = self.workspace / "cache"
        (self.workspace / "docker").mkdir()
        (self.workspace / "docker/config.json").write_text("{}", encoding="utf-8")
        (self.workspace / "trivy.yaml").write_text("{}", encoding="utf-8")
        (self.workspace / "ignore").write_text("", encoding="utf-8")
        self.public_key = self.workspace / "image-signing.pub"
        self.registry_host = region + "-docker.pkg.dev"

    def tool(self, argv, token=None, timeout=300):
        return self.run(argv, workspace=self.workspace,
                        env=child_environment(self.workspace, token, self.registry_host), timeout=timeout)

    def token(self):
        value = self.invoke(["gcloud", "auth", "print-access-token", "--project", self.project]).strip()
        require(bool(value) and not any(c.isspace() for c in value), "image-security-registry-token-required")
        return value

    def prepare(self):
        install_credential_helper(self.workspace, self.registry_host)
        tools = {}
        for name, argv, pattern in (
            ("cosign", ["cosign", "version"], r"GitVersion:\s*(v[0-9]+\.[0-9]+\.[0-9]+)"),
            ("trivy", ["trivy", "--version"], r"Version:\s*([0-9]+\.[0-9]+\.[0-9]+)"),
        ):
            raw = self.tool(argv)
            match = re.search(pattern, raw)
            require(match is not None, "image-security-tool-version-invalid")
            tools[name] = {"version": match[1], "output_sha256": sha(raw)}
        raw, identity = signing_public_key(self.project, self.region, invoke=self.invoke)
        self.public_key.write_text(raw, encoding="utf-8")
        return tools, identity

    def signature(self, image):
        raw = self.tool(["cosign", "verify", "--key", str(self.public_key), "--output=json", image], self.token())
        return signature_summary(raw, image)

    def provenance(self, image, service, source_commit):
        raw = self.tool(["cosign", "verify-attestation", "--key", str(self.public_key),
                         "--type", "slsaprovenance", image], self.token())
        return provenance_summary(raw, image, service, source_commit)

    def scan(self, image):
        token = self.token()
        raw = self.tool(["trivy", "image", "--config", str(self.workspace / "trivy.yaml"),
            "--cache-dir", str(self.cache), "--ignorefile", str(self.workspace / "ignore"),
            "--scanners", "vuln", "--image-src", "remote", "--platform", "linux/amd64",
            "--pkg-types", "os,library", "--list-all-pkgs", "--ignore-unfixed=false",
            "--skip-db-update=false", "--skip-java-db-update=false", "--disable-telemetry",
            "--severity", "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL", "--format", "json", "--exit-code", "0",
            "--no-progress", "--quiet", "--timeout", "15m", image], token, timeout=960)
        result = scan_summary(raw, image)
        result["observed_at"] = stamp()
        result["databases"] = database_summary(self.cache, result["observed_at"])
        return result


def _verify_scan_evidence(value, key, images, bindings, source_commit, environment, profile):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key),
            "image-security-observation-signature-invalid")
    require(value.get("observation_type") == OBSERVATION_TYPE
            and value.get("schema_version") == "1.0" and re.fullmatch(r"ms67-images-[0-9a-f]{32}", value.get("run_id", "")),
            "image-security-observation-identity-required")
    require(value.get("images") == images and value.get("bindings") == bindings
            and value.get("source_commit") == source_commit
            and value.get("cluster_identity_sha256") == profile["cluster_uid_sha256"]
            and value.get("profile_namespace_uid_sha256") == profile["namespace_uid_sha256"]
            and re.fullmatch(HEX64, value.get("environment", {}).get("namespace_uid_sha256", ""))
            and all(value.get("environment", {}).get(k) == v for k, v in environment.items()),
            "image-security-observation-bindings-mismatch")
    require(value.get("application_mutations") == 0 and value.get("credentials_persisted") is False
            and value.get("raw_output_persisted") is False and value.get("production_environment") is False
            and value.get("ms67_complete") is False and value.get("production_ready") is False,
            "image-security-observation-scope-invalid")
    start, end = instant(value.get("started_at")), instant(value.get("finished_at"))
    require(start <= end, "image-security-observation-window-invalid")
    public_key = value.get("verification_key", {})
    number = public_key.get("project_number", "")
    parent = f"locations/{environment['region']}/keyRings/cloudbank-ms67/cryptoKeys/image-signing/cryptoKeyVersions/"
    require(re.fullmatch(HEX64, public_key.get("public_key_sha256", "")) and re.fullmatch(r"[0-9]+", number)
            and any(re.fullmatch(re.escape(f"projects/{p}/" + parent) + r"[1-9][0-9]*", public_key.get("version", ""))
                    for p in (environment["project"], number)) and "SIGN" in public_key.get("algorithm", ""),
            "image-security-verification-key-required")
    require(set(value.get("tools", {})) == {"cosign", "trivy"}, "image-security-tool-evidence-required")
    require(all(re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", t.get("version", ""))
                and re.fullmatch(HEX64, t.get("output_sha256", "")) for t in value["tools"].values()),
            "image-security-tool-version-evidence-required")
    rows = value.get("services")
    require(isinstance(rows, list) and [row.get("service") for row in rows] == list(SERVICES),
            "image-security-eight-service-results-required")
    for row in rows:
        require(row.get("image") == images[row["service"]] and row.get("status") == "passed",
                "image-security-service-result-invalid")
        for kind in ("signature", "provenance"):
            result = row.get(kind, {})
            require(result.get("verified") is True and type(result.get("count")) is int and result["count"] > 0
                    and re.fullmatch(HEX64, result.get("output_sha256", "")), "image-security-verified-claims-required")
        provenance = row["provenance"]
        require(provenance.get("source_commit") == source_commit and isinstance(provenance.get("statement_sha256"), list)
                and 0 < len(provenance["statement_sha256"]) <= provenance["count"]
                and all(re.fullmatch(HEX64, x) for x in provenance["statement_sha256"]),
                "image-security-verified-provenance-source-required")
        scan = row.get("scan", {})
        levels = scan.get("severity_counts", {})
        require(set(levels) == {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
                and all(type(n) is int and n >= 0 for n in levels.values()), "image-security-severity-counts-required")
        require(type(scan.get("high")) is int and type(scan.get("critical")) is int
                and scan["high"] == scan["critical"] == 0
                and scan.get("severity_counts", {}).get("HIGH") == 0
                and scan.get("severity_counts", {}).get("CRITICAL") == 0
                and scan.get("finding_ids") == [] and scan.get("finding_ids_complete") is True
                and re.fullmatch(HEX64, scan.get("scan_sha256", "")), "image-security-zero-high-critical-required")
        require(all(type(scan.get("coverage", {}).get(k)) is int and scan["coverage"][k] > 0
                    for k in ("os_packages", "java_packages")), "image-security-scan-coverage-required")
        scanned = instant(scan.get("observed_at"))
        require(start <= scanned <= end and set(scan.get("databases", {})) == {"db", "java-db"},
                "image-security-scan-window-or-databases-invalid")
        for name, version in (("db", 2), ("java-db", 1)):
            database = scan["databases"][name]
            require(database.get("version") == version and instant(database.get("updated_at")) <= scanned
                    < instant(database.get("next_update")) and re.fullmatch(HEX64, database.get("metadata_sha256", "")),
                    "image-security-current-database-required")
    _verify_live(value, images, ("before",))
    require(set(value.get("deployment_specs_before", {})) == set(SERVICES)
            and all(re.fullmatch(HEX64, h) for h in value["deployment_specs_before"].values()),
            "image-security-deployment-baseline-required")


def _verify_live(value, images, phases):
    for phase in phases:
        live = value.get("live", {}).get(phase, {})
        require(set(live) == set(SERVICES) and all(live[s].get("image") == images[s]
                and type(live[s].get("ready_replicas")) is int and live[s]["ready_replicas"] == 2
                and re.fullmatch(HEX64, live[s].get("pod_identity_sha256", ""))
                for s in SERVICES), "image-security-live-image-checks-required")


def verify_checkpoint(value, key, images, bindings, source_commit, environment, profile, *, at):
    """Accept only complete signed scans stopped by a final transport failure."""
    _verify_scan_evidence(value, key, images, bindings, source_commit, environment, profile)
    require(value.get("status") == "failed" and "scan_checkpoint" not in value
            and value.get("reason") in {
                "operator-command-unavailable-or-timed-out",
                "image-security-checkpoint-upload-unconfirmed",
                "image-security-checkpoint-generation-unconfirmed",
                "image-security-checkpoint-readback-unconfirmed",
            }
            and value.get("failed_phase") in {
                "chatbot-scan",  # Legacy runner mislabeled the completed row's checkpoint.
                "chatbot-checkpoint", "final-live-binding-check", "final-evidence-checkpoint",
            }, "image-security-finalizable-checkpoint-required")
    require(instant(value["finished_at"]) <= instant(at), "image-security-checkpoint-from-future")
    for row in value["services"]:
        require(all(instant(at) < instant(db["next_update"]) for db in row["scan"]["databases"].values()),
                "image-security-checkpoint-databases-expired")


def verify_observation(value, key, images, bindings, source_commit, environment, profile):
    _verify_scan_evidence(value, key, images, bindings, source_commit, environment, profile)
    require(value.get("status") == PASS and not any(k in value for k in ("reason", "failed_phase", "evidence_upload")),
            "image-security-passing-observation-required")
    _verify_live(value, images, ("after",))
    require(value["deployment_specs_before"] == value.get("deployment_specs_after"),
            "image-security-deployment-drift")
    if "scan_checkpoint" in value:
        prior = value["scan_checkpoint"]
        verify_checkpoint(prior, key, images, bindings, source_commit, environment, profile, at=value["finished_at"])
        require(prior["run_id"] != value["run_id"]
                and instant(prior["finished_at"]) <= instant(value.get("finalization_started_at")) <= instant(value["finished_at"])
                and value.get("finalization_key") == prior["verification_key"]
                and all(value.get(k) == prior.get(k) for k in (
                    "started_at", "services", "tools", "verification_key", "deployment_specs_before", "environment"))
                and value["live"]["before"] == prior["live"]["before"],
                "image-security-checkpoint-lineage-invalid")
    else:
        require(not any(k in value for k in ("finalization_started_at", "finalization_key")),
                "image-security-checkpoint-lineage-required")
