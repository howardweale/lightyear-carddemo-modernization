"""L1a graph-off admission. No provider, candidate or private-reference execution."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import time
from urllib import parse, request

from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_repair_controller as ctl
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import public_repair_worker as worker
from lightyear_factory.public_repair_durable import DurablePorts


REPOSITORY = "howardweale/lightyear-carddemo-modernization"
RELEASE_BINDING = "spec/public-answer-key-loader/2026-11-18-r1/RELEASE-BINDING.json"
HELPER = "factory/cobol-runtime/src/org/lightyear/cobol/RecordNumbers.java"
SUITE = "tests/fixtures/reference-execution/public-cases/SUITE.json"
WORKER = "src/lightyear_factory/public_repair_worker.py"
SOURCES = tuple(sorted((
    "src/lightyear_factory/staged_run_admission.py",
    "src/lightyear_factory/public_repair_controller.py",
    "src/lightyear_factory/public_repair_staged.py",
    "src/lightyear_factory/public_repair_durable.py",
    "src/lightyear_factory/public_repair_provider.py",
    "src/lightyear_factory/public_repair_answer_key.py",
    "src/lightyear_factory/public_evaluator_adapter.py",
    "src/lightyear_factory/public_repair_worker_entry.py", WORKER, HELPER, SUITE,
    RELEASE_BINDING,
    "spec/staged-public/2026-11-17-r1/CONTRACT.txt",
    "spec/public-reference-freeze/2026-11-17-wrapper-r1/CONTRACT.txt",
    "spec/public-answer-key-loader/2026-11-18-r1/CONTRACT.txt",
    "spec/public-evaluator/2026-11-17-adapter-r3/CONTRACT.txt",
    "spec/public-repair-durable/2026-11-17-r1/CONTRACT.txt",
    "spec/public-repair-provider/2026-11-17-r1/CONTRACT.txt",
    "spec/public-build-worker/2026-11-17-r1/CONTRACT.txt",
    "spec/intcalc-graph/2026-11-16-public-repair/CONTRACT.txt",
    "spec/staged-run-admission/2026-11-19-r1/CONTRACT.txt",
)))
PROOFS = ("main_green", "mac_tls_1", "ledger_volume", "disk_headroom",
          "public_worker", "measured_bounds_and_deadlines")
PACKAGE = "8496a8c754b0a179888561be69aa06d4655d15e0c54decb891c757bb190d960d"
RATES = dict(unit="quarter-microdollars-per-token", count_input=22,
             generation_input=22, generation_output=99,
             count_billing_assumption_accepted=True, billing_final=False)
RECEIPT_MAX = 65536
TAG = re.compile(r"[A-Za-z0-9][-A-Za-z0-9_.]{0,127}")
OID = re.compile(r"[0-9a-f]{40}")


def check(ok, code):
    ctl.require(ok, "admission-" + code)


def fields(row, names):
    check(type(row) is dict and set(row) == set(names.split()), "fields")


def record(raw):
    check(type(raw) is bytes and 0 < len(raw) <= RECEIPT_MAX, "bytes")
    value = staged.strict(raw)
    check(type(value) is dict, "fields")
    return value


def oid(value):
    return type(value) is str and OID.fullmatch(value) is not None


def checkout(root):
    """Read the named checkout and compare actual module bytes with committed blobs."""
    root = Path(root).resolve(strict=True)

    def git(*args):
        return subprocess.check_output(["git", "--no-replace-objects", "-C", str(root),
                                        *args], stdin=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=20)

    def identity():
        commit, tree = git("show", "-s", "--format=%H %T", "HEAD").decode("ascii").split()
        check(oid(commit) and oid(tree), "checkout")
        return commit, tree

    commit, tree = identity()
    check(Path(os.fsdecode(git("rev-parse", "--show-toplevel").rstrip())).resolve() == root,
          "checkout")
    check(not git("status", "--porcelain=v1", "--untracked-files=all"), "checkout")
    modules = {}
    for name in SOURCES:
        path = root / name
        check(path.resolve(strict=True) == path and path.is_file()
              and path.stat().st_size <= 2097152, "checkout")
        committed = git("show", commit + ":" + name)
        check(path.read_bytes() == committed, "checkout")
        modules[name] = ctl.sha(committed)
    check(identity() == (commit, tree), "checkout")
    return dict(commit=commit, tree=tree, modules=modules)


def check_descriptor(descriptor):
    fields(descriptor, "repository release_id asset_id tag")
    check(descriptor["repository"] == REPOSITORY
          and type(descriptor["tag"]) is str and TAG.fullmatch(descriptor["tag"])
          and all(type(descriptor[k]) is int and descriptor[k] > 0
                  for k in ("release_id", "asset_id")), "publication")


def github_publication(descriptor, deadline):
    """Read only public metadata and the reviewed, two-field H2 commitment asset."""
    check_descriptor(descriptor)
    origin = "https://api.github.com/repos/" + REPOSITORY
    # This reader never attaches authorization headers. Redirects are allowed only
    # to GitHub's public HTTPS Release asset hosts.
    class ReleaseRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            url = parse.urlsplit(newurl)
            check(url.scheme == "https" and url.hostname in
                  ("github.com", "release-assets.githubusercontent.com",
                   "objects.githubusercontent.com") and url.username is None
                  and url.password is None and url.port in (443, None), "publication")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = request.build_opener(request.ProxyHandler({}), ReleaseRedirect())

    def read(url, cap):
        remaining = deadline - time.monotonic()
        check(remaining > 0, "deadline")
        with opener.open(url, timeout=min(10, remaining)) as response:
            body = response.read(cap + 1)
            check(response.status == 200 and 0 < len(body) <= cap, "publication")
        check(time.monotonic() < deadline, "deadline")
        return body

    release = staged.strict(read(origin + "/releases/" + str(descriptor["release_id"]), 1048576))
    check(release["id"] == descriptor["release_id"] and release["tag_name"] == descriptor["tag"]
          and release["draft"] is False, "publication")
    matches = [a for a in release["assets"] if a["id"] == descriptor["asset_id"]]
    check(len(matches) == 1, "publication")
    metadata = matches[0]
    check(metadata["state"] == "uploaded" and metadata["name"] == "COMMITMENT.json"
          and type(metadata["size"]) is int and 0 < metadata["size"] <= RECEIPT_MAX,
          "publication")
    url = ("https://github.com/" + REPOSITORY + "/releases/download/"
           + descriptor["tag"] + "/COMMITMENT.json")
    check(metadata["browser_download_url"] == url, "publication")
    asset = read(url, RECEIPT_MAX)
    check(len(asset) == metadata["size"] and metadata["digest"] == "sha256:" + ctl.sha(asset),
          "publication")
    return asset, dict(descriptor, published_at=release["published_at"],
                       asset_created_at=metadata["created_at"], asset_updated_at=metadata["updated_at"],
                       draft=False, public=True, asset_sha256=ctl.sha(asset))


def verify_publication(descriptor, raw, asset, publication, issued_at):
    check_descriptor(descriptor)
    fields(publication, "repository release_id asset_id tag published_at asset_created_at asset_updated_at "
           "draft public asset_sha256")
    check(all(publication[k] == v and type(publication[k]) is type(v)
              for k, v in descriptor.items()) and publication["draft"] is False
          and publication["public"] is True, "publication")
    obj = record(asset)
    fields(obj, "schema commitment_sha256")
    check(obj["schema"] == "heldout-public-commitment/1"
          and ctl.hash_ok(obj["commitment_sha256"])
          and publication["asset_sha256"] == ctl.sha(asset), "publication")
    committed_at = staged.instant(raw["committed_at"])
    # A release may have existed before this particular asset was uploaded.
    latest = max(staged.instant(publication[k]) for k in ("published_at", "asset_created_at", "asset_updated_at"))
    check(committed_at == latest and latest < issued_at
          and raw["publication_receipt_sha256"] == ctl.digest(publication)
          and raw["commitment_sha256"] == obj["commitment_sha256"], "publication")


def host_qualification(raw):
    row = record(raw)
    fields(row, "schema status operation_id source_commit source_tree qualification_source_commit "
           "qualification_source_tree reviewed_qualification_sha256 profile_sha256 custody_sha256 "
           "postflight_custody_sha256 public_suite_sha256 package_library_sha256 report_sha256 "
           "inventory_sha256 comparison_criterion_met cases probes all_probes_match cleanup "
           "public_only host_resources local_image_id image_digest_bound private_use_authorized limits")
    check(row["schema"] == "ha-public-host-qualification/1" and row["status"] == "CRITERION_MET"
          and all(row[k] is True for k in ("comparison_criterion_met", "cleanup", "public_only"))
          and all(row[k] is False for k in ("image_digest_bound", "private_use_authorized",
                                             "all_probes_match"))
          and row["cases"] == 16 and row["probes"] == 9 and oid(row["source_commit"])
          and oid(row["source_tree"]) and row["package_library_sha256"] == PACKAGE
          and row["public_suite_sha256"] == key.QUALIFICATION["public_suite_sha256"]
          and row["qualification_source_commit"] == key.QUALIFICATION["qualification_commit"]
          and row["qualification_source_tree"] == key.QUALIFICATION["qualification_tree"]
          and row["reviewed_qualification_sha256"] == key.QUALIFICATION["qualification_sha256"]
          and all(ctl.hash_ok(v) for k, v in row.items() if k.endswith("_sha256")), "host")
    return ctl.sha(raw)


def check_evidence(intent, binding, source, key_review, host, proofs, now):
    fields(intent, "schema source_commit source_tree modules_sha256 binding_intent_sha256 "
           "key_release_sha256 host_qualification_sha256 publication proofs rates holds_microdollars")
    check(intent["schema"] == "graph-off-admission-intent/1", "intent")
    check(intent["source_commit"] == source["commit"] and intent["source_tree"] == source["tree"]
          and set(source["modules"]) == set(SOURCES)
          and all(ctl.hash_ok(v) for v in source["modules"].values())
          and intent["modules_sha256"] == binding["implementation_sha256"]
          == ctl.digest(source["modules"]), "source")
    modules = source["modules"]
    check(intent["key_release_sha256"] == modules[RELEASE_BINDING] == key.RELEASE_BINDING_SHA256
          and binding["public_answer_key_sha256"] == key_review.manifest_sha256
          and binding["public_suite_sha256"] == modules[SUITE] == key.QUALIFICATION["public_suite_sha256"],
          "key")
    profile = binding["build_profile"]
    check(binding["worker_source_sha256"] == modules[WORKER]
          and profile["helper_sha256"] == modules[HELPER]
          and profile["jdk_sha256"] == worker.JDK and profile["jre_sha256"] == worker.JRE
          and binding["runtime_profile_sha256"] == ctl.digest(profile), "worker")
    check(intent["host_qualification_sha256"] == host_qualification(host), "host")
    unsealed = {k: v for k, v in binding.items() if k != "authority_sha256"}
    check(intent["binding_intent_sha256"] == ctl.digest(unsealed)
          and ctl.canonical(intent["rates"]) == ctl.canonical(RATES)
          and ctl.canonical(intent["holds_microdollars"]) == ctl.canonical(ctl.HOLDS), "intent")
    check(set(proofs) == set(intent["proofs"]) == set(PROOFS), "proofs")
    for kind in PROOFS:
        # Each bounded envelope binds the expert-reviewed underlying receipt bytes.
        evidence, attachment = proofs[kind]
        row = record(evidence)
        fields(row, "schema kind source_commit source_tree observed_at valid_until passed "
               "receipt_sha256 subject_sha256")
        subjects = {"public_worker": binding["runtime_profile_sha256"],
                    "measured_bounds_and_deadlines": binding["public_context_sha256"]}
        check(row["schema"] == "staged-prerequisite-observation/1" and row["kind"] == kind
              and row["passed"] is True and row["source_commit"] == source["commit"]
              and row["source_tree"] == source["tree"] and type(attachment) is bytes
              and 0 < len(attachment) <= 2097152 and row["receipt_sha256"] == ctl.sha(attachment)
              and row["subject_sha256"] == subjects.get(kind, intent["modules_sha256"])
              and staged.instant(row["observed_at"]) <= now < staged.instant(row["valid_until"])
              and intent["proofs"][kind] == ctl.sha(evidence), "proofs")


class GraphOffAdmission:
    """Single use. Trusted launcher supplies Howard's independent approval digest and public reads."""

    def __init__(self, *, root, authority_root, expected_approval, approval, intent, context,
                 key_binding, key_archive, host, proofs, read_publication=github_publication,
                 clock=time.monotonic, wall=lambda: datetime.now(timezone.utc)):
        self.root = root
        self.authority_root = authority_root
        self.expected_approval = expected_approval
        self.approval = approval
        self.intent = intent
        self.context = context
        self.key_binding = key_binding
        self.key_archive = key_archive
        self.host = host
        self.proofs = proofs
        self.read_publication = read_publication
        self.clock = clock
        self.wall = wall
        self.used = False

    def admit(self, binding_bytes, deadline):
        check(not self.used, "used")
        self.used = True
        try:
            return self._admit(binding_bytes, deadline)
        except ctl.Refused:
            raise
        except Exception:
            raise ctl.Refused("admission-refused") from None

    def _admit(self, binding_bytes, deadline):
        check(self.clock() < deadline, "deadline")
        authority = record(self.approval)
        fields(authority, "schema operator operation_id intent_sha256 approved_at latest_start "
               "mode model graph_mode cap_microdollars window_seconds count_billing_assumption_accepted")
        check(ctl.hash_ok(self.expected_approval) and ctl.sha(self.approval) == self.expected_approval
              and authority["schema"] == "staged-paid-run-approval/1" and authority["operator"] == "Howard"
              and ctl.hash_ok(authority["operation_id"]) and authority["mode"] == "STAGED_PUBLIC"
              and authority["graph_mode"] == "off" and authority["model"] == ctl.MODEL
              and authority["count_billing_assumption_accepted"] is True
              and authority["cap_microdollars"] == ctl.CEILING and authority["window_seconds"] == ctl.WINDOW,
              "authority")
        issued = staged.instant(authority["approved_at"])
        end = staged.instant(authority["latest_start"])
        check(issued <= self.wall() < end and (end-issued).total_seconds() <= ctl.WINDOW, "time")
        binding = record(binding_bytes)
        staged.validate_binding(binding, self.context)
        check(ctl.canonical(binding) == binding_bytes and binding["authority_sha256"] == self.expected_approval
              and binding["approval_timestamp"] == authority["approved_at"], "authority")
        intent = record(self.intent)
        check(authority["intent_sha256"] == ctl.sha(self.intent), "intent")
        source = checkout(self.root)
        reviewed = key.published_key(self.key_binding, "full-intcalc-public-answer-key-20261118-r1",
                                     self.key_archive)
        check_evidence(intent, binding, source, reviewed, self.host, self.proofs, self.wall())
        asset, publication = self.read_publication(intent["publication"], deadline)
        verify_publication(intent["publication"], binding["pre_run_commitment"], asset, publication, issued)
        now = self.wall()
        check(issued <= now < end and self.clock() < deadline, "deadline")
        check(all(now < staged.instant(record(e)["valid_until"]) for e, _ in self.proofs.values()), "proofs")
        receipt = dict(schema="graph-off-admission-receipt/1", binding_sha256=ctl.sha(binding_bytes),
                       authority_sha256=self.expected_approval, operation_id=authority["operation_id"],
                       intent_sha256=authority["intent_sha256"], source_commit=source["commit"],
                       source_tree=source["tree"], publication_sha256=ctl.digest(publication),
                       admitted_at=now.isoformat(), hidden_execution_authorized=False)
        # Fixed owner-managed parent across launches. P3 exclusively creates the operation
        # directory and fsyncs its parent. Any late error leaves the operation spent.
        guard = DurablePorts(self.authority_root, authority["operation_id"], deadline, clock=self.clock)
        try:
            digest = guard.record("admission", receipt)
            check(digest == ctl.sha(ctl.canonical(receipt) + b"\n"), "receipt")
            check(self.clock() < deadline and self.wall() < end, "deadline")
            return dict(binding_sha256=receipt["binding_sha256"], receipt_sha256=digest)
        finally:
            guard.close()
