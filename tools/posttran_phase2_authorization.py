"""Read-only authorization and image preflight, always before attempt reservation."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from lightyear_control_tower.factory_policy import FactoryDecisions, require
from lightyear_factory.tower_authority import proof_contract

REQUEST = "docs/factory/posttran-phase2-authorization-request-2026-10-15.json"
PROOF = "docs/factory/posttran-phase2-authorization-proof-2026-10-15.json"
PUBLIC_KEY = "docs/factory/factory-authority.public.pem"
PLAN = "docs/factory/posttran-phase2-plan-2026-10-15.json"
RETURN_CODES = dict(equal_allowed=[0, 4], equal_other="divergent",
                    exception=dict(scenario="generated:posttran-duplicate-id", candidate=999, twin=12))


def verify_signed(root, plan, head, env, *, now=None):
    root = Path(root)
    require((root/PROOF).is_file(), "phase2-signed-proof-missing")
    proof = json.loads((root/PROOF).read_bytes())
    contract = proof_contract(proof)
    require(contract == json.loads((root/REQUEST).read_bytes()), "phase2-signed-request-binding")
    reader = FactoryDecisions((root/PUBLIC_KEY).read_bytes(), env.get("POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD"))
    reader.verify(proof, "engineering-run-approval", contract, ("approve",))
    details = contract["details"]
    require(details["request_seal"] == plan["content_sha256"], "phase2-signed-plan-binding")
    require(details["observer_sha256"] == plan["bound_files"][".github/workflows/posttran-phase2.yml"], "phase2-signed-workflow-binding")
    expected = dict(Candidate=plan["candidate_files"]["spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java"],
                    Provenance=plan["candidate_files"]["spec/mainframe/posttran-independent/attempt-1/provenance.json"],
                    CompilerImageArchive=plan["twin"]["image_archive_sha256"])
    require(details["class_hashes"] == expected and details["caps"] == {"attempts": 1, "runs": 1}, "phase2-signed-bounds")
    require(plan["retries"] == 0 and plan["return_code_rule"] == RETURN_CODES, "phase2-return-code-rule")
    require(any(s["path"] == PLAN and s["sha256"] == sha256((root/PLAN).read_bytes()).hexdigest()
                and s["commit"] == details["executable_commit"] for s in contract["sources"]), "phase2-signed-source-binding")
    at = now or datetime.now(timezone.utc)
    start, end = [datetime.fromisoformat(details["window"][k]) for k in ("start", "end")]
    require(start <= at < end, "phase2-authorization-window")
    # A commit cannot contain a signature of its own commit hash. The signed
    # executable commit is immutable; its execution PR may add only these two
    # control-plane files. The separate approved-head variable still pins the
    # exact final PR commit. Any code/plan/key change requires renewed approval.
    signed_head = details["executable_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", signed_head, head], cwd=root, check=True, capture_output=True)
    changed = subprocess.check_output(["git", "diff", "--name-only", signed_head, head], cwd=root, text=True).splitlines()
    require(set(changed) <= {REQUEST, PROOF}, "phase2-signed-executable-head-changed")
    return contract


def check_artifact_metadata(artifacts, plan, now):
    rows = [a for a in artifacts if a["name"] == plan["compiler_image_artifact"]]
    require(len(rows) == 1, "phase2-image-artifact-missing-or-ambiguous")
    artifact = rows[0]
    expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
    require(not artifact.get("expired", True) and expires - now >= timedelta(hours=24), "phase2-image-retention-below-24-hours")
    return artifact


def verify_image(plan, repository, *, now=None, run=subprocess.run):
    at = now or datetime.now(timezone.utc)
    prefix = f"repos/{repository}/actions"
    result = run(["gh", "api", f"{prefix}/runs/{plan['preparation_run']}/artifacts?per_page=100"],
                 check=True, capture_output=True, timeout=60)
    listing = json.loads(result.stdout)
    require(listing["total_count"] <= 100, "phase2-artifact-list-incomplete")
    artifact = check_artifact_metadata(listing["artifacts"], plan, at)
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp)/"image.zip"
        with archive.open("wb") as stream:
            run(["gh", "api", f"{prefix}/artifacts/{artifact['id']}/zip"], stdout=stream, check=True, timeout=180)
        with zipfile.ZipFile(archive) as package:
            require(package.namelist().count("compiler-image.tar") == 1, "phase2-image-archive-member")
            hasher = sha256()
            with package.open("compiler-image.tar") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    hasher.update(chunk)
            require(hasher.hexdigest() == plan["twin"]["image_archive_sha256"], "phase2-image-archive-changed")
    # Download time counts against the safety margin.
    check_artifact_metadata([artifact], plan, now or datetime.now(timezone.utc))
    return dict(artifact_id=artifact["id"], expires_at=artifact["expires_at"],
                image_archive_sha256=hasher.hexdigest(), verified_before_reservation=True)
