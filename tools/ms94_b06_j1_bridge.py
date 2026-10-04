"""B06-only J1 observation bridge; imports the inherited J1 predicates unchanged."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, sign_once


def inputs(run, plan):
    verify(plan)
    check(plan.get('j1_unchanged_gate') == 'tools.ms94_v6_gate.evaluate', 'adapter-does-not-own-J1')
    check(plan['qualification_only'] is True and plan['model_calls'] == 0, 'j1-not-zero-model')
    required = {'operations.java', 'checkpoint.json', 'primary-keys.json', 'comparison-register.json',
                'datatype-inventory.json', 'invoice-type-contract.json', 'history-bound.json',
                'oracle-entry-multisets.json', 'postgresql-entry-multisets.json'}
    check(required <= set(plan['inputs_sha256']), 'j1-required-input-binding')
    check(plan['harness_sha256'] == plan['inputs_sha256']['operations.java'], 'j1-candidate-binding')
    for name, sha in plan['inputs_sha256'].items():
        check(Path(name).name == name, 'j1-nested-input')
        bound_file(Path(run) / 'inputs', name, sha)
    from tools.ms94_b06_runtime_contract import admit_contract
    admit_contract(plan, Path(run).name)
    return {'journey': 'J1'}


def admit(run, signer):
    from tools.ms94_a3_entry_v2 import admit as inherited_admit
    run = Path(run); plan = read_json(run / 'plan.json'); inputs(run, plan)
    entry = inherited_admit(run, signer)
    return sign_once(run / 'b06-entry-admission.json', {
        'artifact_type': 'ms94-b06-native-entry/1', 'plan_sha256': plan['content_sha256'],
        'checkpoint_sha256': entry['checkpoint_sha256'], 'journey': 'J1',
        'inherited_entry_sha256': entry['content_sha256'], 'native_entry_checks': entry['native_entry_checks'],
        'passed': True, 'candidate_started': False}, signer)


def replay_entry(run, public_key):
    from tools.ms94_a3_entry import check as inherited_check
    run = Path(run); plan = read_json(run / 'plan.json'); inputs(run, plan)
    entry = read_json(run / 'a3-entry-admission.json'); wrapper = read_json(run / 'b06-entry-admission.json')
    check(verify_envelope(entry, public_key) and verify_envelope(wrapper, public_key), 'j1-entry-signature')
    expected = inherited_check(run)
    check(all(entry.get(k) == v for k, v in expected.items() if k != 'content_sha256'), 'j1-entry-replay-differs')
    check(wrapper['plan_sha256'] == plan['content_sha256'] and wrapper['inherited_entry_sha256'] == entry['content_sha256'] and
          wrapper['native_entry_checks'] == expected['native_entry_checks'] and wrapper['journey'] == 'J1' and
          wrapper['passed'] is True and wrapper['candidate_started'] is False, 'j1-entry-wrapper-binding')
    return wrapper


def evaluate(run, public_key):
    from tools.ms94_v6_gate import evaluate as unchanged_judge
    run = Path(run)
    replay_entry(run, public_key)
    from tools.ms94_b06_admission import replay_clocks, native_pair_tables
    replay_clocks(run, public_key); native_pair_tables(run)
    # Calls the original qualified judge, including invoice type, observer and
    # all original business predicates. Its original gate file is retained.
    return unchanged_judge(run)
