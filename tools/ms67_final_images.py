#!/usr/bin/env python3
"""Create and verify metadata-only OCI packaging revisions for the MS67 drills."""
from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lightyear_data.cloudbank_journeys import SERVICES, hashed, require
from lightyear_data.cloudbank_image_security import ImageScanner, child_environment, SOURCE_URI
from lightyear_data.cloudbank_sql_recovery import invoke, verified, write_signed
from lightyear_data.contracts import seal

PROJECT = "lightyear-ms67-nonproduction"
REGION = "us-west1"
REGISTRY = REGION + "-docker.pkg.dev/" + PROJECT + "/cloudbank-ms67"
BASE_SOURCE = "22ac6a4c0dcb39fbfdb7eab28cad5eebc4b9ea8e"
REVISION_LABEL = "ai.lightyr.ms67.packaging-revision"


def downloaded(url, limit=300 * 1024 * 1024):
    request = urllib.request.Request(url, headers={"User-Agent": "LIGHTYEAR-MS67-final-drills"})
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = response.read(limit + 1)
    require(len(raw) <= limit, "tool-download-size-limit")
    return raw


def release_asset(repo, version, name, target):
    value = json.loads(downloaded(f"https://api.github.com/repos/{repo}/releases/tags/{version}", 4*1024*1024))
    require(value.get("tag_name") == version and not value.get("draft") and not value.get("prerelease"),
            "tool-release-identity-invalid")
    rows = [a for a in value.get("assets", []) if a.get("name") == name]
    require(len(rows) == 1, "official-tool-asset-required")
    asset = rows[0]
    url = f"https://github.com/{repo}/releases/download/{version}/{name}"
    require(asset.get("browser_download_url") == url and re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest", "")),
            "official-tool-sha256-required")
    raw = downloaded(url)
    require(hashlib.sha256(raw).hexdigest() == asset["digest"][7:], "tool-asset-checksum-mismatch")
    target.write_bytes(raw)
    return {"repository": repo, "version": version, "asset": name, "sha256": asset["digest"][7:]}


def install_tools(work):
    binary = work / "bin"
    binary.mkdir(exist_ok=True)
    system, machine = platform.system(), platform.machine()
    require((system, machine) in {("Linux", "x86_64"), ("Darwin", "arm64"), ("Darwin", "x86_64")},
            "supported-linux-amd64-or-macos-operator-required")
    os_name, cpu = ("linux" if system == "Linux" else "darwin"), ("arm64" if machine == "arm64" else "amd64")
    trivy_platform = "Linux-64bit" if system == "Linux" else "macOS-" + ("ARM64" if cpu == "arm64" else "64bit")
    assets = [release_asset("sigstore/cosign", "v3.1.2", f"cosign-{os_name}-{cpu}", binary / "cosign")]
    archive = work / "trivy.tar.gz"
    assets.append(release_asset("aquasecurity/trivy", "v0.74.0", f"trivy_0.74.0_{trivy_platform}.tar.gz", archive))
    with tarfile.open(archive) as stream:
        members = [m for m in stream.getmembers() if m.name in {"trivy", "./trivy"} and m.isfile()]
        require(len(members) == 1 and members[0].size <= 300*1024*1024, "bounded-trivy-executable-required")
        with stream.extractfile(members[0]) as source:
            (binary / "trivy").write_bytes(source.read())
    for name in ("cosign", "trivy"):
        (binary / name).chmod(0o755)
    requirement = (ROOT / "factory/cloudbank/platform-qualification/gke/image-security-requirements.txt").read_text()
    match = re.search(r"distlib==([0-9.]+) --hash=sha256:([0-9a-f]{64})", requirement)
    require(match is not None, "pinned-distlib-requirement-required")
    version, digest = match.groups()
    package = json.loads(downloaded(f"https://pypi.org/pypi/distlib/{version}/json", 4*1024*1024))
    wheels = [r for r in package["urls"] if r.get("packagetype") == "bdist_wheel"
              and r.get("digests", {}).get("sha256") == digest and r.get("url", "").startswith("https://files.pythonhosted.org/")]
    require(len(wheels) == 1, "pinned-distlib-wheel-required")
    raw = downloaded(wheels[0]["url"], 4*1024*1024)
    require(hashlib.sha256(raw).hexdigest() == digest, "distlib-wheel-checksum-mismatch")
    wheel = work / "distlib.whl"
    wheel.write_bytes(raw)
    sys.path.insert(0, str(wheel))
    os.environ["PATH"] = str(binary) + os.pathsep + os.environ.get("PATH", "")
    return assets


def packaging_proof(service, base, candidate, run_id):
    """Reject layer, architecture or execution-setting changes, even if signed."""
    require(base["RootFS"] == candidate["RootFS"] and bool(base["RootFS"].get("Layers")),
            "candidate-must-preserve-every-filesystem-layer")
    require(all(base.get(k) == candidate.get(k) for k in ("Os", "Architecture", "Variant")),
            "candidate-platform-changed")
    before, after = dict(base["Config"]), dict(candidate["Config"])
    labels = before.pop("Labels", None) or {}
    require(after.pop("Labels", None) == {**labels, REVISION_LABEL: run_id}, "candidate-label-delta-invalid")
    require(before == after, "candidate-runtime-configuration-changed")
    def reference(value):
        refs = [r for r in value.get("RepoDigests", []) if r.startswith(REGISTRY + "/" + service + "@sha256:")]
        require(len(refs) == 1, "unique-built-image-digest-required")
        return refs[0]
    original, revised = reference(base), reference(candidate)
    require(original != revised and base["Id"] != candidate["Id"], "candidate-image-digest-did-not-change")
    return {"service": service, "baseline_image": original, "candidate_image": revised,
            "rootfs_sha256": hashed(base["RootFS"]), "runtime_configuration_sha256": hashed(before),
            "baseline_config_digest": base["Id"], "candidate_config_digest": candidate["Id"],
            "revision_label": REVISION_LABEL, "revision_value": run_id,
            "scope": "metadata-only OCI packaging revision; no application or filesystem change"}


def prepare(context, work):
    images, run_id = context["images"], context["run_id"]
    require(re.fullmatch(r"ms67-final-[0-9a-f]{32}", run_id), "final-run-id-invalid")
    for service in SERVICES:
        require(re.fullmatch(re.escape(REGISTRY + "/" + service) + r"@sha256:[0-9a-f]{64}", images[service]),
                "baseline-registry-image-invalid")
        target = work / "candidates" / service
        target.mkdir(parents=True, exist_ok=True)
        (target / "Dockerfile").write_text(f"FROM {images[service]}\nLABEL {REVISION_LABEL}=\"{run_id}\"\n")
    import shlex
    commands = ["#!/bin/sh", "set -eu"]
    for service in SERVICES:
        original = images[service]
        tag = REGISTRY + "/" + service + ":" + run_id
        folder = str(work / "candidates" / service)
        for argv in (["docker", "pull", original], ["docker", "build", "--platform=linux/amd64", "--pull=false", "--tag", tag, folder],
                     ["docker", "push", tag]):
            commands.append(shlex.join(argv))
        for image, suffix in ((original, "base"), (tag, "candidate")):
            commands.append(shlex.join(["docker", "image", "inspect", image]) + " > " +
                            shlex.quote(str(work / f"{service}-{suffix}.inspect.json")))
    (work / "package.sh").write_text("\n".join(commands) + "\n")


def finish_packaging(context, work):
    proofs = []
    for service in SERVICES:
        base = json.loads((work / f"{service}-base.inspect.json").read_text())[0]
        candidate = json.loads((work / f"{service}-candidate.inspect.json").read_text())[0]
        original = context["images"][service]
        base["RepoDigests"] = [original]
        candidate["RepoDigests"] = [r for r in candidate["RepoDigests"]
                                   if r.startswith(REGISTRY + "/" + service + "@") and r != original]
        proofs.append(packaging_proof(service, base, candidate, context["run_id"]))
    (work / "packaging.json").write_text(json.dumps(proofs))
    return proofs


def build(context, work):
    proofs = []
    for service in SERVICES:
        original = context["images"][service]
        tag = REGISTRY + "/" + service + ":" + context["run_id"]
        # No shell and no credentials in arguments or files.
        for argv in (["docker", "pull", original],
                     ["docker", "build", "--platform=linux/amd64", "--pull=false", "--tag", tag,
                      str(work / "candidates" / service)], ["docker", "push", tag]):
            subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1200)
        base = json.loads(invoke(["docker", "image", "inspect", original]))[0]
        revised = json.loads(invoke(["docker", "image", "inspect", tag]))[0]
        # Docker may retain multiple repo digest aliases. Select the resolved
        # reference for this pull/push without accepting an arbitrary alias.
        revised["RepoDigests"] = [r for r in revised["RepoDigests"]
                                  if r.startswith(REGISTRY + "/" + service + "@") and r != original]
        base["RepoDigests"] = [original]
        proofs.append(packaging_proof(service, base, revised, context["run_id"]))
        print("MS67_CANDIDATE_BUILT=" + service, flush=True)
    (work / "packaging.json").write_text(json.dumps(proofs))


def secure(context, work, key, signer):
    assets = install_tools(work)
    proofs = json.loads((work / "packaging.json").read_text())
    require([p["service"] for p in proofs] == list(SERVICES), "eight-packaging-proofs-required")
    scanner_root = work / "scanner"
    scanner_root.mkdir(exist_ok=True)
    scanner = ImageScanner(PROJECT, REGION, scanner_root)
    tools, identity = scanner.prepare()
    require(tools["cosign"]["version"] == "v3.1.2" and tools["trivy"]["version"] == "0.74.0",
            "reviewed-security-tool-versions-required")
    # Use the sole enabled key version through the key URI supported by cosign.
    # prepare() has verified that exactly one enabled signing version exists.
    uri = "gcpkms://" + identity["version"].rsplit("/cryptoKeyVersions/", 1)[0]
    evidence = []
    for proof in proofs:
        service, image = proof["service"], proof["candidate_image"]
        require(proof["baseline_image"] == context["images"][service]
                and proof["revision_value"] == context["run_id"], "packaging-input-binding-mismatch")
        baseline_signature = scanner.signature(proof["baseline_image"])
        baseline_provenance = scanner.provenance(proof["baseline_image"], service, BASE_SOURCE)
        predicate = {"builder": {"id": "lightyear-ms67-operator"}, "buildType": "https://lightyear.ai/cloudbank/ms67",
            "invocation": {"parameters": {"service": service, "packaging_proof_sha256": hashed(proof),
                                          "cloud_build_id": os.environ["MS67_FINAL_BUILD_ID"]}},
            "materials": [{"uri": SOURCE_URI, "digest": {"sha1": context["controller_commit"]}},
                          {"uri": image, "digest": {"sha256": image.split("@sha256:")[1]}},
                          {"uri": proof["baseline_image"], "digest": {"sha256": proof["baseline_image"].split("@sha256:")[1]}}]}
        path = work / ("predicate-" + service + ".json")
        path.write_text(json.dumps(predicate))
        for args in (["sign", "--yes", "--key", uri, image],
                     ["attest", "--yes", "--key", uri, "--type", "slsaprovenance", "--predicate", str(path), image]):
            env = child_environment(scanner_root, scanner.token(), REGION + "-docker.pkg.dev")
            completed = subprocess.run(["cosign", *args], env=env, cwd=scanner_root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=600)
            require(completed.returncode == 0, "candidate-signing-failed-" + service)
        row = {"service": service, "packaging": proof, "signature": scanner.signature(image),
               "provenance": scanner.provenance(image, service, context["controller_commit"]),
               "baseline_signature": baseline_signature, "baseline_provenance": baseline_provenance,
               "scan": scanner.scan(image)}
        evidence.append(row)
        write_signed(work / ("candidate-security-" + service + ".json"), row, key, signer)
        require(row["scan"]["high"] == 0 and row["scan"]["critical"] == 0,
                "candidate-high-or-critical-vulnerability-" + service)
        print("MS67_CANDIDATE_SIGNED_VERIFIED_SCANNED=" + service, flush=True)
    lock = seal({"schema_version": "1.0", "lock_type": "lightyear-cloudbank-ms65-image-lock", "release": "0.65.0",
                 "source_ms64_receipt_sha256": context["bindings"]["ms64_receipt_sha256"],
                 "images": [{"service": p["service"], "reference": p["candidate_image"]} for p in proofs]})
    result = {"schema_version": "1.0", "observation_type": "lightyear-ms67-final-candidate-security",
              "run_id": context["run_id"], "controller_commit": context["controller_commit"],
              "cloud_build_id": os.environ["MS67_FINAL_BUILD_ID"],
              "bindings": context["bindings"], "candidate_lock": lock, "services": evidence,
              "tools": tools, "tool_assets": assets, "signing_key": identity,
              "status": "passed", "credentials_persisted": False, "ms67_complete": False,
              "scan_reuse_scope": "Fresh candidate scan applies to the byte-identical baseline filesystem; both image signatures and provenance verified"}
    write_signed(work / "candidate-security.json", result, key, signer)
    return json.loads((work / "candidate-security.json").read_text())


def verify_result(value, context, key):
    verified(value, key)
    require(value.get("observation_type") == "lightyear-ms67-final-candidate-security"
            and value.get("status") == "passed" and value.get("credentials_persisted") is False
            and all(value.get(k) == context[k] for k in ("run_id", "controller_commit", "bindings")),
            "candidate-security-context-invalid")
    from lightyear_data.cloudbank_production_readiness import validate_image_lock
    lock = value.get("candidate_lock", {})
    require(not validate_image_lock(lock, context["bindings"]["ms64_receipt_sha256"]), "candidate-lock-invalid")
    candidates = {r["service"]: r["reference"] for r in lock["images"]}
    require([r.get("service") for r in value.get("services", [])] == list(SERVICES), "eight-candidate-results-required")
    require(value.get("tools", {}).get("cosign", {}).get("version") == "v3.1.2"
            and value.get("tools", {}).get("trivy", {}).get("version") == "0.74.0", "candidate-reviewed-tools-required")
    for row in value["services"]:
        service, proof, scan = row["service"], row["packaging"], row["scan"]
        require(proof.get("baseline_image") == context["images"][service]
                and proof.get("candidate_image") == candidates[service]
                and candidates[service].split("@")[1] != context["images"][service].split("@")[1]
                and proof.get("revision_label") == REVISION_LABEL and proof.get("revision_value") == context["run_id"]
                and all(re.fullmatch(r"[0-9a-f]{64}", proof.get(k, "")) for k in
                        ("rootfs_sha256", "runtime_configuration_sha256"))
                and proof.get("baseline_config_digest") != proof.get("candidate_config_digest"), "candidate-packaging-proof-invalid")
        require(all(re.fullmatch(r"sha256:[0-9a-f]{64}", proof.get(k, "")) for k in
                    ("baseline_config_digest", "candidate_config_digest")), "candidate-config-digests-required")
        for kind in ("signature", "provenance", "baseline_signature", "baseline_provenance"):
            result = row.get(kind, {})
            require(result.get("verified") is True and type(result.get("count")) is int and result["count"] > 0
                    and re.fullmatch(r"[0-9a-f]{64}", result.get("output_sha256", "")), "candidate-verified-signature-required")
        require(row["provenance"].get("source_commit") == context["controller_commit"]
                and row["baseline_provenance"].get("source_commit") == BASE_SOURCE, "candidate-source-chain-invalid")
        require(scan.get("critical") == scan.get("high") == 0 and scan.get("finding_ids") == []
                and scan.get("finding_ids_complete") is True
                and scan.get("severity_counts", {}).get("HIGH") == scan.get("severity_counts", {}).get("CRITICAL") == 0
                and all(type(scan.get("coverage", {}).get(k)) is int and scan["coverage"][k] > 0
                        for k in ("os_packages", "java_packages"))
                and re.fullmatch(r"[0-9a-f]{64}", scan.get("scan_sha256", "")), "candidate-scan-coverage-or-findings-invalid")
        from lightyear_data.cloudbank_image_security import instant
        scanned = instant(scan.get("observed_at"))
        require(set(scan.get("databases", {})) == {"db", "java-db"}, "candidate-scan-databases-required")
        for name, version in (("db", 2), ("java-db", 1)):
            db = scan["databases"][name]
            require(db.get("version") == version and instant(db.get("updated_at")) <= scanned < instant(db.get("next_update"))
                    and re.fullmatch(r"[0-9a-f]{64}", db.get("metadata_sha256", "")), "candidate-current-scan-database-required")
    return candidates


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "secure"))
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--signer", required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    key = os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"]
    context = verified(json.loads(args.context.read_text()), key)
    require(invoke(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip() == context["controller_commit"],
            "candidate-controller-source-mismatch")
    args.work.mkdir(parents=True, exist_ok=True)
    if args.action == "prepare":
        prepare(context, args.work)
    else:
        finish_packaging(context, args.work)
        result = secure(context, args.work, key, args.signer)
        verify_result(result, context, key)
        uri = f"gs://{PROJECT}-ms67-evidence/final-closeout/{context['run_id']}/candidate-security.json"
        invoke(["gcloud", "storage", "cp", str(args.work / "candidate-security.json"), uri, "--if-generation-match=0"], timeout=180)
        require(json.loads(invoke(["gcloud", "storage", "cat", uri])) == result, "candidate-evidence-readback-mismatch")
        print("MS67_CANDIDATE_EVIDENCE_READBACK=VERIFIED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
