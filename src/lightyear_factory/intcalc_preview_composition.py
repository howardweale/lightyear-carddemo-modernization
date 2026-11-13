"""C2 preview composition core and offline CLI; never a P5 admission route.

Trusted ports are controller code, not plugins or candidate-supplied callbacks.
They must be qualified and bound before live integration. This proposal supplies
no live bootstrap, credential procedure, compiler launcher or verifier adapter.
The CLI refuses admit/run rather than substituting an unreviewed implementation.
"""
from dataclasses import dataclass
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import stat
import zipfile
import threading
import time

SCHEMA = "full-intcalc-preview-result/1"
SCOPE = "NOT-P5/public-CBACT04C-only"
ROLES = ("planner", "builder-attempt1", "analysis-attempt1", "builder-repair1", "analysis-attempt2")
VERDICTS = ("MATCH", "EXPECTED_REFUSAL", "DIFFERENT", "REFUSAL_NOT_OBSERVED",
            "EXECUTION_FAILED", "TIMEOUT", "OUTPUT_CONTRACT_VIOLATION", "NOT_RUN", "FAULT")
SUCCESS = frozenset(("MATCH", "EXPECTED_REFUSAL"))
UNSAFE = frozenset(("TIMEOUT", "NOT_RUN", "FAULT"))
FEEDBACK_SCHEMA = "full-intcalc-feedback-counts/1"
FEEDBACK_HASH = "5c1a6f7ae6feba059b05417bfc8fb911e405c542f0ad18a32f595d8e397f3aa6"
LIMIT_HASH = "01daf03f89c6b250a1679c266e1daca5e5ae3831b2371db7b0356842d8323ad2"
CONTEXT_HASH = "38712491400e8839d99fe6bfbee77dd278633bd9f42e0bce614d699e770ac767"
ALLOWLIST_HASH = "7591a32fa00320d970e9a10a5e9f2be2a82d06907cc36c537f8ab1c2ddf7e3cb"
MODEL = "gpt-5.4-2026-03-05"
CAP = 9_460_000
MAX_CONTEXT_ARCHIVE = 2 * 1024 * 1024
MAX_CONTEXT_TOTAL = 128 * 1024
MAX_CONTEXT_MEMBERS = 64
ROLE_INSTRUCTIONS = {
    "planner": "Plan the full public CBACT04C rewrite from the supplied public context; return one plain-text plan in the field \"text\".",
    "builder-attempt1": "Implement the public CBACT04C rewrite using the supplied public context and plan. The field \"source\" must contain the complete text of one Java 21 file, Main.java, with default-package public class Main, using only the JDK; return the full file, not a patch or diff.",
    "analysis-attempt1": "Explain how to improve the first public candidate using only the supplied public context, generated artifacts and verdict-class counts; return plain text in the field \"text\".",
    "builder-repair1": "Repair the public candidate using the supplied public context, generated artifacts and verdict-class counts. The field \"source\" must contain the complete text of one Java 21 file, Main.java, with default-package public class Main, using only the JDK; return the full file, not a patch or diff.",
    "analysis-attempt2": "Summarize the remaining limitations of the repaired public candidate using only the supplied public context, generated artifacts and verdict-class counts; return plain text in the field \"text\"."
}
ROLE_INSTRUCTIONS_SHA256 = "07e223b8b91ecf4fa99668e26b7d490425f32cb09bffda936a467e4ecedd785d"
SLOT_HOLD = 1_892_000
PREREQUISITES = frozenset(("exact_implementations_green", "macos_admission_green",
    "native_arm64_c1_green", "operator_admission_procedure", "spend_authority",
    "count_billing", "local_images", "disk_capacity", "trusted_build_gate_adapter",
    "request_bound_proof", "public_context_review", "exact_run_approval"))
HASH_FIELDS = frozenset(("binding_sha256", "controller_source_manifest_sha256",
    "gate_manifest_sha256", "case_manifest_sha256", "runtime_manifest_sha256",
    "runtime_config_sha256", "toolchain_manifest_sha256", "javac_sha256", "jar_sha256",
    "context_sha256", "allowlist_sha256", "feedback_schema_sha256", "named_limit_sha256",
    "request_bound_proof_sha256", "public_context_approval_sha256"))


class CompositionRefused(ValueError):
    """Only fixed codes; never emit verifier, credential or exception contents."""


def require(ok, code):
    if not ok:
        raise CompositionRefused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def is_hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate-json-key")
            result[key] = value
        return result
    def reject(_):
        raise CompositionRefused("non-integer-number")
    try:
        require(type(raw) is bytes and len(raw) <= 4 * 1024 * 1024, "json-size")
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                          parse_float=reject, parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise CompositionRefused("invalid-json") from None


def context_members(archive, allowlist_raw):
    """Decode hash-bound public ZIP members in memory; never extract to disk."""
    require(type(archive) is bytes and len(archive) <= MAX_CONTEXT_ARCHIVE, "context-archive-size")
    allowlist = strict_json(allowlist_raw)
    require(type(allowlist) is dict and allowlist.get("schema") == "full-intcalc-model-allowlist/1"
            and allowlist.get("model_inputs_only") is True
            and allowlist.get("candidate_and_oracle_execution") is False, "context-allowlist-schema")
    expected = allowlist.get("files")
    require(type(expected) is dict and 0 < len(expected) <= MAX_CONTEXT_MEMBERS, "context-member-count")
    def safe_name(name):
        require(type(name) is str and name and "\\" not in name and ":" not in name
                and "\x00" not in name and not name.startswith("/")
                and all(part not in ("", ".", "..") for part in name.split("/")), "context-member-name")
    total = 0
    for name, metadata in expected.items():
        safe_name(name)
        require(type(metadata) is dict and type(metadata.get("bytes")) is int
                and 0 <= metadata["bytes"] <= MAX_CONTEXT_TOTAL
                and is_hash(metadata.get("sha256")), "context-member-metadata")
        total += metadata["bytes"]
    require(total <= MAX_CONTEXT_TOTAL, "context-total-size")
    try:
        with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
            entries = bundle.infolist()
            names = [entry.filename for entry in entries]
            require(len(names) == len(set(names)), "context-duplicate-member")
            require(set(names) == set(expected), "context-exact-member-set")
            decoded = {}
            for entry in entries:
                safe_name(entry.orig_filename)
                require(entry.orig_filename == entry.filename, "context-member-name")
                safe_name(entry.filename)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                require(not entry.is_dir() and not entry.external_attr & 0x10
                        and mode in (0, stat.S_IFREG), "context-nonregular-member")
                require(not entry.flag_bits & (0x1 | 0x40), "context-encrypted-member")
                require(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "context-compression")
                metadata = expected[entry.filename]
                require(entry.file_size == metadata["bytes"], "context-member-size")
                with bundle.open(entry, "r") as stream:
                    raw = stream.read(metadata["bytes"] + 1)
                require(len(raw) == metadata["bytes"], "context-member-size")
                require(digest(raw) == metadata["sha256"], "context-member-hash")
                decoded[entry.filename] = raw.decode("utf-8", errors="strict")
            return decoded
    except (zipfile.BadZipFile, zipfile.LargeZipFile, UnicodeError, RuntimeError,
            NotImplementedError, EOFError, OSError):
        raise CompositionRefused("invalid-public-context-archive") from None


def validate_packet(packet):
    """Structural binding check, expressly NOT approval authentication."""
    fields = HASH_FIELDS | {"schema", "controller_platform", "runtime_platform", "emulation",
        "byte_policy_sha256", "run_budget_seconds", "cap_microdollars", "prerequisites"}
    require(type(packet) is dict and set(packet) == fields, "packet-fields")
    require(packet["schema"] == "full-intcalc-composition-packet/1", "packet-schema")
    require(all(is_hash(packet[name]) for name in HASH_FIELDS), "packet-hashes")
    require(packet["controller_platform"] == "darwin/arm64"
            and packet["runtime_platform"] == "linux/arm64" and packet["emulation"] is False,
            "native-arm64-required")
    require(packet["byte_policy_sha256"] == "STRICT" or is_hash(packet["byte_policy_sha256"]),
            "explicit-byte-policy")
    require(type(packet["run_budget_seconds"]) is int and packet["run_budget_seconds"] == 8100,
            "fixed-budget")
    require(type(packet["cap_microdollars"]) is int and packet["cap_microdollars"] == CAP, "fixed-cap")
    require(packet["context_sha256"] == CONTEXT_HASH and packet["allowlist_sha256"] == ALLOWLIST_HASH,
            "reviewed-public-context")
    require(packet["feedback_schema_sha256"] == FEEDBACK_HASH
            and packet["named_limit_sha256"] == LIMIT_HASH, "feedback-binding")
    rows = packet["prerequisites"]
    require(type(rows) is dict and set(rows) == PREREQUISITES, "prerequisite-inventory")
    for row in rows.values():
        require(type(row) is dict and set(row) == {"status", "evidence_sha256"}, "prerequisite-fields")
        require(row["status"] in ("MISSING", "PRESENT") and
                (row["evidence_sha256"] is None if row["status"] == "MISSING" else is_hash(row["evidence_sha256"])),
                "prerequisite-evidence")
    return digest(canonical(packet))


def prepare(packet):
    packet_hash = validate_packet(packet)
    return {"schema": "full-intcalc-composition-preflight/1", "packet_sha256": packet_hash,
            "missing": sorted(k for k, v in packet["prerequisites"].items() if v["status"] != "PRESENT"),
            "structural_only": True, "authority_authenticated": False, "admission_ready": False,
            "live_bootstrap_available": False, "qualified": False}


def feedback(verdicts):
    require(type(verdicts) is tuple and len(verdicts) == 10
            and all(type(v) is str and v in VERDICTS for v in verdicts), "complete-verdict-inventory")
    return {"schema": FEEDBACK_SCHEMA, "verdict_counts": {v: verdicts.count(v) for v in VERDICTS}}


def validate_feedback(value):
    require(type(value) is dict and set(value) == {"schema", "verdict_counts"}
            and value["schema"] == FEEDBACK_SCHEMA, "feedback-fields")
    counts = value["verdict_counts"]
    require(type(counts) is dict and set(counts) == set(VERDICTS)
            and all(type(n) is int and 0 <= n <= 10 for n in counts.values())
            and sum(counts.values()) == 10, "feedback-counts")
    return value


@dataclass(frozen=True)
class PhaseWindow:
    deadline_monotonic: float
    original_deadline_monotonic: float
    cleanup_seconds: int = 5


@dataclass(frozen=True)
class BuildResult:
    source_sha256: str
    artifact_sha256: str
    runtime_platform: str
    runtime_manifest_sha256: str
    runtime_config_sha256: str
    toolchain_manifest_sha256: str
    javac_sha256: str
    jar_sha256: str
    receipt_sha256: str
    cleanup_confirmed: bool
    completed: bool


@dataclass(frozen=True)
class GateResult:
    artifact_sha256: str
    gate_manifest_sha256: str
    case_manifest_sha256: str
    runtime_manifest_sha256: str
    runtime_platform: str
    byte_policy_sha256: str
    verdicts: tuple
    receipt_sha256: str
    cleanup_confirmed: bool
    completed: bool


class Composition:
    """One-process, one-use orchestration, with qualified trusted ports required.

    ports.authenticate(packet) authenticates authority, evidence, platform, disk,
    source hashes and images; a PRESENT field is never enough. ports.admit takes
    only packet (private credentials stay inside the trusted port), consumes the
    admission nonce and returns the real admission object. ports.transport builds
    the real PreviewTransport. prove_request binds the exact projection and proves
    its conservative token bound; no byte/token heuristic is supplied here.
    build/gate must enforce PhaseWindow including reap and return typed minimal
    records. No per-case report or build diagnostic crosses these interfaces.
    These ports are not dynamically loadable by this module or its CLI.
    """
    def __init__(self, packet, public_context, public_allowlist, ports, *, clock=time.monotonic):
        self._packet = strict_json(canonical(packet))
        self._packet_hash = validate_packet(self._packet)
        require(type(public_context) is bytes and digest(public_context) == CONTEXT_HASH
                and type(public_allowlist) is bytes and digest(public_allowlist) == ALLOWLIST_HASH,
                "public-bundle-hash")
        self._context = context_members(public_context, public_allowlist)
        self._ports, self._clock = ports, clock
        self._pid, self._lock = os.getpid(), threading.Lock()
        self._started = False
        self._last = None
        self._roles = {role: "NOT_RUN" for role in ROLES}
        self._attempts = []
        self._artifacts = {}
        self._holds = 0
        self._admission = None

    def _now(self):
        now = self._clock()
        require(os.getpid() == self._pid and type(now) in (int, float) and math.isfinite(now), "clock-or-process")
        require(self._last is None or now >= self._last, "clock-regressed")
        self._last = now
        require(self._admission is not None and now < self._admission.deadline_monotonic - 15,
                "original-deadline")
        return now

    def _window(self):
        now = self._now()
        return PhaseWindow(min(now + 600, self._admission.deadline_monotonic - 15),
                           self._admission.deadline_monotonic)

    def _after_phase(self, window):
        require(self._now() < window.deadline_monotonic, "phase-deadline")

    def _record(self, name, value):
        # Trusted durable O_EXCL ledger; no candidate path is accepted.
        self._ports.record_once(name, strict_json(canonical(value)))

    def _schema(self, role):
        field = "source" if role.startswith("builder") else "text"
        return {"type": "object", "properties": {field: {"type": "string"}},
                "required": [field], "additionalProperties": False}

    def _artifact(self, role, value):
        field = "source" if role.startswith("builder") else "text"
        require(type(value) is dict and set(value) == {field} and type(value[field]) is str
                and 0 < len(value[field].encode("utf-8")) <= 128000, "artifact-contract")
        return strict_json(canonical(value))

    def _send(self, role, projection_feedback=None):
        self._now()
        require(self._roles[role] == "NOT_RUN" and self._holds + SLOT_HOLD <= CAP, "role-or-cap")
        # The sole context constructor: known public bundle + generated artifacts
        # + one exact count projection. No runtime diagnostics or verifier record.
        payload = {"public_context": self._context,
                   "generated_artifacts": self._artifacts, "feedback": projection_feedback}
        if projection_feedback is not None:
            validate_feedback(projection_feedback)
        require(digest(canonical(ROLE_INSTRUCTIONS)) == ROLE_INSTRUCTIONS_SHA256, "role-instructions-drift")
        projection = {"model": MODEL, "instructions": ROLE_INSTRUCTIONS[role],
                      "input": canonical(payload).decode("utf-8"),
                      "text": {"format": {"type": "json_schema", "name": "c2_artifact",
                                           "strict": True, "schema": self._schema(role)}}}
        request = self._ports.prove_request(role, strict_json(canonical(projection)))
        require(canonical(request.projection) == canonical(projection)
                and request.projection_sha256 == digest(canonical(projection))
                and request.bound_proof_sha256 == self._packet["request_bound_proof_sha256"]
                and request.public_context_approval_sha256 == self._packet["public_context_approval_sha256"]
                and type(request.token_upper_bound) is int and 0 < request.token_upper_bound <= 100000,
                "reviewed-request-proof")
        self._now()
        # Reserve irreversibly before calling transport. If validation or durable
        # recording fails after here, conservative full hold stays consumed.
        self._roles[role] = "FAILED_CONSUMED"
        self._holds += SLOT_HOLD
        self._record(role + "-composition-start.json", {"role": role, "hold_microdollars": SLOT_HOLD,
            "projection_sha256": request.projection_sha256, "packet_sha256": self._packet_hash})
        value, evidence = self._transport.complete(role, request)
        self._now()
        artifact = self._artifact(role, value)
        require(type(evidence) is dict and evidence.get("role") == role and evidence.get("status") == "COMPLETED"
                and evidence.get("observed_tier") == "flex" and evidence.get("model") == MODEL
                and evidence.get("retries") == 0 and evidence.get("attempts") == 1
                and evidence.get("artifact_sha256") == digest(canonical(artifact)), "transport-evidence")
        self._record(role + "-composition-complete.json", {"role": role, "artifact_sha256": digest(canonical(artifact))})
        self._roles[role] = "COMPLETED"
        self._artifacts[role] = artifact
        return artifact

    def _attempt(self, number, source):
        window = self._window()
        built = self._ports.build(number, source, window)
        self._after_phase(window)
        require(type(built) is BuildResult and built.completed is True and built.cleanup_confirmed is True,
                "build-or-cleanup-fault")
        require(built.source_sha256 == digest(source.encode("utf-8"))
                and is_hash(built.artifact_sha256) and is_hash(built.receipt_sha256), "build-artifact-join")
        for name in ("runtime_platform", "runtime_manifest_sha256", "runtime_config_sha256", "toolchain_manifest_sha256", "javac_sha256", "jar_sha256"):
            require(getattr(built, name) == self._packet[name], "build-platform-toolchain-join")
        window = self._window()
        result = self._ports.gate(number, built, window)
        self._after_phase(window)
        require(type(result) is GateResult and result.completed is True and result.cleanup_confirmed is True,
                "gate-or-cleanup-fault")
        require(result.artifact_sha256 == built.artifact_sha256 and is_hash(result.receipt_sha256), "gate-artifact-join")
        for name in ("gate_manifest_sha256", "case_manifest_sha256", "runtime_manifest_sha256", "runtime_platform", "byte_policy_sha256"):
            require(getattr(result, name) == self._packet[name], "gate-binding-join")
        counts = feedback(result.verdicts)
        record = {"attempt": number, "feedback": counts, "build_receipt_sha256": built.receipt_sha256,
                  "gate_receipt_sha256": result.receipt_sha256, "artifact_sha256": built.artifact_sha256}
        self._attempts.append(record)
        self._record("attempt-" + str(number) + ".json", record)
        # Private eligibility decision. Completed receipts alone do not make
        # TIMEOUT/FAULT/NOT_RUN candidate failures eligible for another send.
        require(not any(counts["verdict_counts"][v] for v in UNSAFE), "non-candidate-fault")
        return all(v in SUCCESS for v in result.verdicts), counts

    def _result(self, status):
        return {"schema": SCHEMA, "scope": SCOPE, "qualified": False,
            "production_controller_receipt": False, "status": status,
            "packet_sha256": self._packet_hash, "roles": dict(self._roles),
            "attempts": strict_json(canonical(self._attempts)),
            "reserved_microdollars": self._holds, "billing_final": False, "holds_released": False,
            "feedback_observations": len(self._attempts), "named_feedback_limit_sha256": LIMIT_HASH,
            "resume": False, "retry": False, "authentication": "local-unsigned-evidence-only"}

    def run(self):
        with self._lock:
            require(not self._started, "session-consumed")
            self._started = True
            try:
                require(not prepare(self._packet)["missing"], "missing-prerequisite")
                # Authority authentication is a trusted integration obligation,
                # not a claim inferred from a supplied JSON hash or boolean.
                require(self._ports.authenticate(strict_json(canonical(self._packet))) is True, "authority-not-authenticated")
                self._admission = self._ports.admit(strict_json(canonical(self._packet)))
                start, end = self._admission.started_monotonic, self._admission.deadline_monotonic
                require(type(start) in (int, float) and type(end) in (int, float) and math.isfinite(start)
                        and math.isfinite(end) and end == start + 8100, "admission-deadline")
                receipt = self._admission.public_receipt()
                require(receipt.get("schema") == SCHEMA and receipt.get("scope") == SCOPE
                        and receipt.get("qualified") is False and receipt.get("production_controller_receipt") is False
                        and receipt.get("status") == "ADMITTED_ONLY"
                        and receipt.get("binding_sha256") == self._packet["binding_sha256"], "admission-binding")
                self._last = start
                self._now()
                self._record("composition-admitted.json", {"packet_sha256": self._packet_hash,
                    "binding_sha256": self._packet["binding_sha256"], "run_budget_seconds": 8100})
                self._transport = self._ports.transport(self._admission)
                self._send("planner")
                source = self._send("builder-attempt1")["source"]
                passed, first_feedback = self._attempt(1, source)
                if passed:
                    status = "MATCH_FIRST_ATTEMPT"
                else:
                    # Same frozen serialized projection is supplied twice, not a
                    # fresh observation and never an expanded per-case report.
                    frozen = canonical(first_feedback)
                    self._send("analysis-attempt1", strict_json(frozen))
                    source = self._send("builder-repair1", strict_json(frozen))["source"]
                    passed, second_feedback = self._attempt(2, source)
                    if passed:
                        status = "MATCH_AFTER_REPAIR"
                    else:
                        self._send("analysis-attempt2", second_feedback)
                        status = "CANDIDATE_FAIL"
                result = self._result(status)
                self._record("composition-result.json", result)
                return result
            except BaseException as error:
                result = self._result("STOPPED")
                try:
                    self._record("composition-stopped.json", result)
                except Exception:
                    # No pass result, resend, refund, or diagnostic leak on a
                    # failed evidence write. The original error is not printed.
                    pass
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise CompositionRefused("composition-stopped-no-resume") from None


def verify_result(value):
    """Offline structural verification; no signature/production qualification."""
    fields = {"schema", "scope", "qualified", "production_controller_receipt", "status", "packet_sha256",
        "roles", "attempts", "reserved_microdollars", "billing_final", "holds_released", "feedback_observations",
        "named_feedback_limit_sha256", "resume", "retry", "authentication"}
    require(type(value) is dict and set(value) == fields, "result-fields")
    require(value["schema"] == SCHEMA and value["scope"] == SCOPE and value["qualified"] is False
            and value["production_controller_receipt"] is False, "preview-only")
    require(is_hash(value["packet_sha256"]) and value["named_feedback_limit_sha256"] == LIMIT_HASH,
            "result-binding")
    require(value["authentication"] == "local-unsigned-evidence-only" and
            all(value[k] is False for k in ("billing_final", "holds_released", "resume", "retry")), "result-limits")
    roles = value["roles"]
    require(type(roles) is dict and set(roles) == set(ROLES)
            and all(v in ("NOT_RUN", "COMPLETED", "FAILED_CONSUMED") for v in roles.values()), "result-roles")
    states = [roles[role] for role in ROLES]
    consumed = sum(v != "NOT_RUN" for v in states)
    require(all(v != "NOT_RUN" for v in states[:consumed])
            and all(v == "NOT_RUN" for v in states[consumed:]), "result-role-prefix")
    failed = [i for i, v in enumerate(states) if v == "FAILED_CONSUMED"]
    require(not failed or failed == [consumed - 1], "result-failed-role-terminal")
    require(type(value["reserved_microdollars"]) is int and value["reserved_microdollars"] == consumed * SLOT_HOLD
            and value["reserved_microdollars"] <= CAP, "result-cost")
    attempts = value["attempts"]
    require(type(attempts) is list and len(attempts) <= 2 and type(value["feedback_observations"]) is int
            and value["feedback_observations"] == len(attempts), "result-observations")
    for index, row in enumerate(attempts, 1):
        require(type(row) is dict and set(row) == {"attempt", "feedback", "build_receipt_sha256", "gate_receipt_sha256", "artifact_sha256"}
                and type(row["attempt"]) is int and row["attempt"] == index
                and all(is_hash(row[k]) for k in ("build_receipt_sha256", "gate_receipt_sha256", "artifact_sha256")), "attempt-record")
        validate_feedback(row["feedback"])
    status = value["status"]
    require(status in ("MATCH_FIRST_ATTEMPT", "MATCH_AFTER_REPAIR", "CANDIDATE_FAIL", "STOPPED"), "result-status")
    if status != "STOPPED":
        expected = {"MATCH_FIRST_ATTEMPT": 2, "MATCH_AFTER_REPAIR": 4, "CANDIDATE_FAIL": 5}[status]
        require([roles[r] for r in ROLES] == ["COMPLETED"] * expected + ["NOT_RUN"] * (5 - expected), "result-role-order")
        require(len(attempts) == (1 if expected == 2 else 2), "result-attempt-count")
        successes = [sum(row["feedback"]["verdict_counts"][v] for v in SUCCESS) == 10 for row in attempts]
        require(successes == {"MATCH_FIRST_ATTEMPT": [True], "MATCH_AFTER_REPAIR": [False, True],
                              "CANDIDATE_FAIL": [False, False]}[status], "result-outcome-join")
        require(not any(row["feedback"]["verdict_counts"][v] for row in attempts for v in UNSAFE), "result-fault")
    return {"schema_valid": True, "authentication_verified": False, "qualified": False,
            "scope": SCOPE, "status": status}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "admit", "run"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(not args.qualify, "preview-cannot-qualify")
        require(args.command not in ("admit", "run"), "qualified-live-bootstrap-not-supplied")
        require(args.input is not None and is_hash(args.sha256), "exact-public-input-required")
        # No recursive directory, environment, credential, adapter or runtime discovery.
        require(not args.input.is_symlink() and args.input.is_file(), "regular-public-input")
        require(args.input.stat().st_size <= 4 * 1024 * 1024, "input-size")
        with args.input.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        require(digest(raw) == args.sha256, "public-input-hash")
        value = strict_json(raw)
        result = prepare(value) if args.command == "prepare" else verify_result(value)
        print(canonical(result).decode("utf-8"))
        return 0
    except (CompositionRefused, OSError, ValueError):
        print('{"status":"REFUSED","qualified":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
