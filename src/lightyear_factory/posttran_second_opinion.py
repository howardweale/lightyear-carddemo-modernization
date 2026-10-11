"""No-call preregistration and independent-input boundary for POSTTRAN."""
import json
from pathlib import Path
from hashlib import sha256
from lightyear_control_tower.decisions import digest,verify_envelope
from lightyear_mainframe.zos_bindings import ROOT,load_bindings,dataset_binding

DIRECTORY=ROOT/'docs/factory/posttran-second-opinion'


def input_allowlist():
    paths={'spec/mainframe/public-source/CBTRN02C.cbl','spec/mainframe/public-source/POSTTRAN.jcl'}
    for dd in ('ACCTFILE','TCATBALF','XREFFILE','TRANFILE','DALYTRAN','DALYREJS'):
        paths.add(dataset_binding(load_bindings(),'POSTTRAN','STEP15',dd)['copybook'])
    base=ROOT/'tests/mainframe/fixtures/arrival-rehearsal/POSTTRAN-run1-2026-10-05'
    # Only before images; no run.json, expected outputs, receipt or review sheet.
    paths.update(p.relative_to(ROOT).as_posix() for p in (base/'before').glob('*') if p.is_file())
    paths.add('docs/factory/posttran-second-opinion/public-contract.md')
    return sorted(paths)


def prepare():
    b05=json.loads((ROOT/'docs/calibration/idempiere-ms94/stage-b-05/plan.json').read_bytes())
    cost=json.loads((ROOT/'docs/calibration/idempiere-ms94/stage-b-05/cost-estimate.json').read_bytes());usage=cost['observed_b04_usage']
    phases={}
    for number,calls,hours,dollars in ((1,3,2,25),(2,2,1,17)):
        phases[str(number)]=dict(attempts=calls,model_calls=calls,compilations=calls,hours=hours,
            input_tokens=250000*calls,output_tokens=16000*calls,per_call_input_tokens=250000,
            per_call_output_tokens=16000,api_equivalent_hard_cap_usd=dollars,
            estimate_usd=[round(cost['all_115_calls_short_usd']/115*calls,2),round(cost['all_115_calls_long_no_cache_sensitivity_usd']/115*calls,2)],
            worst_case_token_cap_usd=round(calls*(250000*25+16000*75)/1000000,2))
    value=dict(schema='posttran-independent-preregistration/1',run_class='engineering',status='awaiting-exact-budget-approval',
        execution_authorized=False,model_calls_made=0,oracle_status='provisional',human_candidate_edits=False,
        source_commit='59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e',
        client=b05['model_and_public_runtime']['builder_client'],model='gpt-6-astra',reasoning_effort='high',
        service_tier='standard',server_snapshot_limitation='Exact requested model string; official page provides no dated snapshot. No immutable server identity claim.',
        inputs={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in input_allowlist()},
        prompts={p:sha256((DIRECTORY/p).read_bytes()).hexdigest() for p in ('phase1-work-order.md','phase2-work-order.md')},
        phases=phases,budget_basis=dict(path='docs/calibration/idempiere-ms94/stage-b-05/cost-estimate.json',content_sha256=cost['content_sha256'],observed_usage=usage,
        intcalc='Three successful public INTCALC three-way cases and one refusal establish harness scope only; their model usage is not recorded. No invented INTCALC call-cost average.',
        intcalc_receipt_sha256=sha256((ROOT/'docs/factory/three-way-reconciliation-result.json').read_bytes()).hexdigest()),
        scenarios=dict(public=['posttran-public','posttran-missing-card','posttran-missing-account','posttran-expired-account'],
            generated=['posttran-'+n for n in ('zero','positive','negative','credit-equal','credit-above','expiry-equal','expiry-before','missing-card','missing-account','empty','duplicate-id','new-category','solver-credit-false','solver-credit-true')],
            generator_commit='88dbf55',required_before_call='Exact generated input manifest and hashes sealed; no subset selection'),
        phase1_gate=['compile Java21','structural contract','own-output conservation/rejection/repeatability invariants'],
        independence=['no twin outputs','no invariant results to builder','no human review sheet','no twin-driven repair'],
        phase2_gate='All phase1 disagreements human-adjudicated with source lines; all twin defects resolved; separate phase2 approval',
        pricing_source='https://developers.openai.com/api/docs/pricing',pricing_checked_date='2026-10-11',
        publish='All attempts, failures, missing usage, disagreements, adjudications and source hashes regardless of outcome')
    value['content_sha256']=digest(value)
    return value


def require_inputs(manifest):
    expected=input_allowlist()
    if set(manifest)!=set(expected):raise ValueError('independent-builder-input-allowlist')
    for p,h in manifest.items():
        if sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('independent-builder-input-hash')


def require_phase2(register,decisions=None,operator_key=None):
    if not operator_key or not decisions or not verify_envelope(decisions,operator_key) or decisions.get('register_sha256')!=digest(register):
        raise ValueError('unresolved-or-twin-defect-blocks-phase2')
    rows=decisions.get('decisions',[])
    if (len(rows)!=len(register) or {r['id'] for r in rows}!={r['id'] for r in register}
        or any(r.get('adjudication') not in ('candidate-defect','neither-defective') or not r.get('source_lines') for r in rows)):
        raise ValueError('unresolved-or-twin-defect-blocks-phase2')


if __name__=='__main__':
    print(json.dumps(prepare(),indent=2,sort_keys=True))
