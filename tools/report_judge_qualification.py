"""Verify preserved native qualification evidence and resolve conditional scope review."""
from pathlib import Path
import json
from lightyear_calibration.contracts import require,read_json,verify
from lightyear_calibration.journey_order import save,file_hash
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools.qualify_journey_judge import EXPECTED_REJECTION


def report(root):
    root=Path(root).resolve();area=root/'factory/idempiere/qualification'
    signer=JourneySigner(root);key=signer.public
    acceptance=read_json(area/'references/operations/scope-acceptance.json')
    require(verify_envelope(acceptance,key),'Scope acceptance signature failed')
    names=['reference-operations-02',*('negative-'+f+'-01' for f in EXPECTED_REJECTION)]
    attempts=[];implementations=None
    for name in names:
        output=root/'work/ms93'/name
        require((output/'receipt.json').exists(),'Qualification attempt is not terminal: '+name)
        receipt=read_json(output/'receipt.json');run=root/read_json(output/'run.json')['run_directory']
        require(verify_envelope(receipt,key),'Receipt signature failed')
        require(receipt==read_json(run/'receipt.json'),'Receipt copies differ')
        plan=read_json(run/'plan.json');verify(plan)
        gate=read_json(run/'gate.json');verify(gate)
        cleanup=read_json(run/'cleanup.json')
        require(verify_envelope(cleanup,key) and cleanup['complete'],'Cleanup not complete')
        require(receipt['plan_sha256']==plan['content_sha256'] and
                receipt['gate_sha256']==gate['content_sha256'],'Receipt binding failed')
        require(receipt['reference_sha256']==acceptance['reference_sha256'],'Reviewed reference differs')
        require(receipt['qualification_check_passed'] and not receipt['autonomous_success']
                and receipt['model_calls']==0,'Qualification failed or mislabeled')
        frozen=plan['implementation_sha256']
        for relative,sha in frozen.items():
            require(file_hash(run/'qualification-source'/relative)==sha,'Archived implementation changed')
        judges={p:s for p,s in frozen.items() if p.startswith('src/lightyear_calibration/')}
        if implementations is None:implementations=judges
        else:require(judges==implementations,'Judge implementation changed across controls')
        attempts.append({'run_id':run.name,'fault':receipt['fault'],'status':receipt['status'],
                         'receipt_sha256':receipt['content_sha256'],'gate_sha256':gate['content_sha256'],
                         'cleanup_verified':True,'elapsed_seconds':receipt['elapsed_seconds'],
                         'negative_checks':receipt.get('negative_checks',{})})
    value=signer.sign({'artifact_type':'native-judge-qualification-summary','status':'passed-bounded-qualification',
        'scenario':'operations','reference_sha256':acceptance['reference_sha256'],
        'scope_acceptance_sha256':acceptance['content_sha256'],
        'scope_review_status':'accepted-condition-satisfied','source_line_by_line_review_claimed':False,
        'attempts':attempts,'positive_native_lanes':2,'negative_native_lanes':8,
        'judge_implementation_sha256':implementations,'model_calls':0,'autonomous_success':False,
        'excluded_preserved_attempts':['work/ms93/reference-operations-01'],
        'limits':['Reference test equipment, not autonomous success or a reliability rate.',
                  'Rollback mutation models a leaked committed row; it does not disable engine rollback.',
                  'These four negative controls do not prove the judge rejects every possible defect.',
                  'Purchasing, reusable-component qualification and a new generation campaign are separate gates.']})
    save(area/'operations-qualification.json',value)
    return value


if __name__=='__main__':
    value=report(Path('.'));print(json.dumps({'status':value['status'],'scope_review_status':value['scope_review_status']}))
