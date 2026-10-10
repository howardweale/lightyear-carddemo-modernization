"""B06 native evidence admission; no model transport and no synthetic admission.

This is deliberately separate from J1's unchanged judge. Complete raw table
captures are authenticated before a business predicate can see their contents.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from lightyear_calibration.contracts import canonical, read_json, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_calibration.ms94_v3_errors import BusinessViolation
from lightyear_calibration.ms94_v3_journey_verify import entries
from lightyear_calibration.native_reconciliation import rows, state
from lightyear_control_tower.decisions import verify_envelope
from lightyear_control_tower.status_export import atomic_new

LANES = ("oracle", "postgresql")


class EvidenceFailure(ValueError):
    """Missing, changed or incomplete equipment evidence; never a business verdict."""


def check(condition, code):
    if not condition:
        raise EvidenceFailure(code)


def bound_file(root, name, expected):
    root = Path(root).resolve()
    relative = Path(name)
    check(not relative.is_absolute() and ".." not in relative.parts,
          "binding-path-escaped")
    path = root / relative
    check(path.resolve().is_relative_to(root) and
          not any(p.is_symlink() for p in (path, *path.parents)), "binding-link-refused")
    check(path.is_file() and file_hash(path) == expected, "bound-file-changed")
    return path


def verify_inputs(run, plan):
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(plan, run)
    verify(plan)
    check(plan["artifact_type"] == "ms94-b06-native-pair-plan/1", "wrong-native-plan")
    if plan['journey'] == 'J1':
        from tools.ms94_b06_j1_bridge import inputs
        return inputs(run, plan)
    check(plan["journey"] in ("J2", "J3"), "adapter-does-not-own-J1")
    check(plan["model_calls"] == 0 and plan["qualification_only"] is True,
          "not-zero-model-qualification")
    required = {'operations.java', 'private-expectations.json', 'checkpoint.json', 'primary-keys.json',
                'comparison-register.json', 'datatype-inventory.json',
                *(l + '-entry-multisets.json' for l in LANES)}
    if plan['journey'] == 'J3':
        required.update({'private-work-order.json', 'private-selection.json'})
    else:
        required.add('history-bound.json')
    check(required <= set(plan['inputs_sha256']), 'required-input-binding-missing')
    check(plan['harness_sha256'] == plan['inputs_sha256']['operations.java'], 'candidate-input-binding')
    for name, expected in plan["inputs_sha256"].items():
        check(Path(name).name == name, "nested-private-input-refused")
        bound_file(run / "inputs", name, expected)
    if plan.get('execution_admission_version') == 3:
        from tools.ms94_b06_register_inputs import admit
        admit(run, plan)
        from tools.ms94_b06_bytecode_policy import validate_policy
        validate_policy(plan['posting_observer'])
    contract = read_json(run / "inputs/private-expectations.json")
    check(hashlib.sha256(canonical(contract)).hexdigest() == plan["private_expectations_sha256"],
          "private-expectations-changed")
    check(contract["journey"] == plan["journey"], "private-expectation-journey")
    from tools.ms94_b06_runtime_contract import admit_contract
    admit_contract(plan, run.name)
    return contract


def sign_once(path, body, signer):
    check(not Path(path).exists(), "preserve-existing-signed-record")
    record = signer.sign(body)
    check(verify_envelope(record, signer.public), "new-signature-invalid")
    atomic_new(Path(path), record)
    persisted = read_json(path)
    check(persisted == record and verify_envelope(persisted, signer.public),
          "persisted-signature-invalid")
    return record


def full_entry(run, signer):
    """The inherited schema/60 constraint probes/complete multisets run first."""
    run = Path(run)
    plan = read_json(run / "plan.json")
    contract = verify_inputs(run, plan)
    if plan['journey'] == 'J1':
        from tools.ms94_b06_j1_bridge import admit
        return admit(run, signer)
    findings = entries(run, {"operations": run / "cases/operations/1"})
    before = {}
    for lane in LANES:
        expected = read_json(run / 'inputs' / (lane + '-entry-multisets.json'))
        _, before[lane] = complete_tables(run / 'cases/operations/1/baseline' / lane / 'entry', lane, expected)
    from tools.ms94_b06_expectations import verify_private_derivation
    verify_private_derivation(run, contract, before)
    return sign_once(run / "b06-entry-admission.json", {
        "artifact_type": "ms94-b06-native-entry/1",
        "plan_sha256": plan["content_sha256"],
        "checkpoint_sha256": read_json(run / "inputs/checkpoint.json")["content_sha256"],
        "journey": plan["journey"], "native_entry_checks": findings,
        "passed": True, "candidate_started": False,
    }, signer)


def replay_entry(run, public_key):
    run = Path(run)
    plan = read_json(run / "plan.json")
    verify_inputs(run, plan)
    if plan['journey'] == 'J1':
        from tools.ms94_b06_j1_bridge import replay_entry as j1_replay
        return j1_replay(run, public_key)
    saved = read_json(run / "b06-entry-admission.json")
    check(verify_envelope(saved, public_key) and saved["passed"] is True and
          saved["plan_sha256"] == plan["content_sha256"] and
          saved["journey"] == plan["journey"] and saved["candidate_started"] is False,
          "entry-binding-invalid")
    check(saved["checkpoint_sha256"] ==
          read_json(run / "inputs/checkpoint.json")["content_sha256"], "entry-checkpoint-changed")
    check(entries(run, {"operations": run / "cases/operations/1"}) == saved["native_entry_checks"],
          "full-entry-replay-differs")
    return saved


def complete_tables(folder, lane, expected_tables):
    """Read every raw row, including tables not mentioned by the business judge."""
    snapshot = state(folder, lane)
    # The column catalog also contains views. Completeness is bound to the
    # independently admitted all-base-table inventory, not inferred from views.
    check(set(expected_tables) == set(snapshot["tables"]), "incomplete-table-inventory")
    return snapshot, {name: rows(folder, item) for name, item in snapshot["tables"].items()}


def native_pair_tables(run):
    before, after, bindings = {}, {}, {}
    folder = Path(run) / "cases/operations/1"
    for lane in LANES:
        expected = read_json(Path(run) / "inputs" / (lane + "-entry-multisets.json"))
        old, before[lane] = complete_tables(folder / "baseline" / lane / "entry", lane, expected)
        new, after[lane] = complete_tables(folder / "after" / lane, lane, expected)
        check(old["structure"] == new["structure"], "native-structure-changed")
        check(set(before[lane]) == set(after[lane]), "native-table-set-changed")
        bindings[lane] = {"before_sha256": old["content_sha256"],
                          "after_sha256": new["content_sha256"],
                          "all_tables_replayed": len(after[lane])}
    return before, after, bindings


def row_delta(before, after):
    old, new = Counter(map(canonical, before)), Counter(map(canonical, after))
    def select(records, counts):
        result = []
        for row in records:
            key = canonical(row)
            if counts[key]:
                result.append(row)
                counts[key] -= 1
        return result
    return select(before, old - new), select(after, new - old)


def utc(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise EvidenceFailure('clock-timestamp-invalid') from exc
    check(result.tzinfo is not None, "clock-timezone-missing")
    return result.astimezone(timezone.utc)


def replay_clocks(run, public_key):
    """Trusted host envelopes, real database clocks, and no clock-setting runtime."""
    run = Path(run)
    plan = read_json(run / "plan.json")
    from tools.ms94_b06_runtime_contract import admit_contract, clock_record, verify_runtime
    spec = admit_contract(plan, run.name)
    calendar = plan["calendar"]
    verify(calendar)
    check(calendar["clock_mode"] == "unmodified-real-time", "clock-mode-changed")
    low, high = utc(calendar["period_start_utc"]), utc(calendar["period_end_exclusive_utc"])
    evidence = read_json(run / "b06-clock-evidence.json")
    check(verify_envelope(evidence, public_key) and
          evidence["plan_sha256"] == plan["content_sha256"], "clock-evidence-binding")
    check(set(evidence["lanes"]) == set(LANES), "clock-lane-missing")
    for lane, record in evidence["lanes"].items():
        start, end = utc(record["host_start_utc"]), utc(record["host_end_utc"])
        check(low <= start <= end < high, "host-period-boundary")
        check(record["monotonic_seconds"] >= 0 and
              abs((end - start).total_seconds() - record["monotonic_seconds"]) <= 5,
              "host-clock-discontinuity")
        execution_path = run / "cases/operations/1/execution" / lane / "execution.json"
        execution = read_json(execution_path)
        verify(execution)
        check(clock_record(record.get("queries"), execution, spec["clock_stages"]) == record,
              "clock-record-does-not-replay")
        check(record["execution_sha256"] == execution["content_sha256"], "clock-execution-binding")
        for position, host in (("before", start), ("after", end)):
            stamp = execution["native_clock_" + position]["value"]
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                # Native capture sessions are independently admitted as UTC.
                observed = observed.replace(tzinfo=timezone.utc)
            check(low <= observed < high and abs((observed - host).total_seconds()) <= 5,
                  "native-real-clock-diverged")
    verify_runtime(evidence["runtime"], spec)
    return {"clock_replayed": True, "clock_sha256": evidence["content_sha256"]}


def classify_failure(error):
    from tools.ms94_b06_candidate_result import CandidateTimeout
    if isinstance(error, CandidateTimeout):
        return "candidate-timeout"
    if isinstance(error, BusinessViolation):
        return "business-failure"
    if isinstance(error, EvidenceFailure):
        return "insufficient-evidence"
    return "equipment-failure"
