"""Prepare a complete Phase 2 plan in CI without running either application."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BASE_IMAGE = 'ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b'
OUTPUTS = ('ACCTFILE', 'TCATBALF', 'TRANFILE', 'DALYREJS')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
def save(path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def bound_files():
    paths = set()
    for name in ('src/lightyear_mainframe', 'src/carddemo_oracle', 'spec/mainframe', 'tests/mainframe/fixtures', 'tools/legacy_twin'):
        paths.update(p for p in (ROOT / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.update(ROOT / name for name in ('tools/prepare_posttran_phase2.py', 'tools/run_posttran_phase2.py',
        'tools/check_posttran_attempt1_phase1.py', 'tools/posttran_phase2_authorization.py', '.github/workflows/posttran-phase2.yml',
        'docs/factory/keep-or-fix-register.json', 'docs/factory/twin-limits.md'))
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}


def prepare(output, image_id, archive):
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise ValueError('CI-only-plan-preparation')
    from lightyear_mainframe.legacy_twin import PUBLIC_SCENARIOS, public_inputs
    from lightyear_mainframe.scenario_generation import manifest, case
    from lightyear_mainframe.records import load_copybook
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
    import re
    if not re.fullmatch('sha256:[0-9a-f]{64}', image_id): raise ValueError('compiler-image-id-required')
    scenarios = []
    names = [('public', n) for n, (job, _) in PUBLIC_SCENARIOS.items() if job == 'POSTTRAN']
    names += [('generated', r['id']) for r in manifest() if r['job'] == 'POSTTRAN']
    for kind, name in names:
        job, meta, images, _ = case(name) if kind == 'generated' else public_inputs(name)
        scenarios.append(dict(id=kind + ':' + name, kind=kind, name=name, job=job,
            input_sha256={dd: sha(raw) for dd, raw in sorted(images.items())}, timestamp=meta['candidate_timestamp']))
    fields = {}
    for dd in OUTPUTS:
        b = dataset_binding(load_bindings(), 'POSTTRAN', 'STEP15', dd)
        layout = load_copybook(ROOT / b['copybook'])
        fields[dd] = dict(copybook=b['copybook'], keys=b['keys'], fields=[dict(path=f.path, filler=f.filler) for f in layout.fields])
    candidate = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted((ROOT / 'spec/mainframe/posttran-independent/attempt-1').rglob('*')) if p.is_file()}
    if candidate['spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java'] != '1b501ff62f1578064d6867c18ad1a0a412d8d7c6e91bb82c91d52bb538134186': raise ValueError('candidate-changed')
    from tools.posttran_phase2_authorization import RETURN_CODES
    value = dict(schema='posttran-phase2-plan/2', prepared_on=datetime.now(timezone.utc).date().isoformat(),
        preparation_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        preparation_run=int(os.environ['GITHUB_RUN_ID']), compiler_image_artifact='posttran-phase2-compiler-image',
        generation_attempt=1, model_calls=0, execution_authorized=False, candidate_files=candidate,
        twin=dict(compiler_package='3.1.2-5.1ubuntu1', image_id=image_id, base_image=BASE_IMAGE,
            image_archive_sha256=sha(archive.read_bytes()), source_sha256=sha((ROOT / 'spec/mainframe/public-source/CBTRN02C.cbl').read_bytes()),
            oracle_status='provisional', zos_confirmation=False),
        bound_files=bound_files(), scenarios=scenarios, scenario_count=len(scenarios), compared_outputs=fields,
        normalization_rules=[], comparison='Exact output bytes, including filler, record order, signs and timestamps; decode differences only for diagnosis.',
        abend_contract=dict(candidate_source_code=999, candidate_process_code=231, twin_process_code=12,
            scope='Only attempt-1 POSTTRAN duplicate-WRITE abend; neither code substitutes for the other elsewhere.'),
        keep_or_fix=dict(duplicate_id='keep non-atomic balance posting before duplicate WRITE abend',
            cycle_debit_sign='keep source sign behaviour: public workload has 38 rejects, not 23'),
        outcomes=dict(equivalent='All four complete output byte streams and scoped return-code contract agree, and the fixed keep-or-fix checks pass.',
            divergent='Both executions yield readable complete outputs but at least one byte or scoped return code differs.',
            indeterminate='A required input binding, execution receipt, output, or decoder is missing or invalid.'),
        return_code_rule=RETURN_CODES,
        retries=0, candidate_repair_authorized=False, qualification_credit=False, release_authorized=False)
    value['content_sha256'] = digest(value)
    output.mkdir(parents=True, exist_ok=False); save(output / 'posttran-phase2-plan-2026-10-16.json', value)
    save(output / 'preparation-not-authorization.json', dict(
        schema='posttran-phase2-authorization-request/1', plan_sha256=value['content_sha256'],
        workflow='.github/workflows/posttran-phase2.yml', generation_attempt=1, run_attempt=1,
        approved=False, effective=False, requested_from='Howard', exact_execution_head=None,
        required_approval='Explicit approval of this plan hash and execution commit; then configure POSTTRAN_PHASE2_APPROVED_PLAN and POSTTRAN_PHASE2_APPROVED_HEAD.',
        scope='One CI run; candidate bytes unchanged; no model calls, repair, release, or z/OS claim.'))
    print(json.dumps({'plan_sha256': value['content_sha256'], 'scenarios': len(scenarios), 'execution_authorized': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path); p.add_argument('--image-id', required=True); p.add_argument('--archive', type=Path, required=True)
    a = p.parse_args(); prepare(a.output, a.image_id, a.archive)
