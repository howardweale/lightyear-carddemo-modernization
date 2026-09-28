"""Signed, failure-preserving status of qualification equipment; never a factory rate."""
from pathlib import Path
from collections import Counter
import json
from lightyear_calibration.contracts import require,read_json,verify
from lightyear_calibration.journey_order import save,file_hash
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_control_tower.decisions import verify_envelope


def report(root):
    root=Path(root).resolve();signer=JourneySigner(root);attempts=[]
    area=root/'factory/idempiere/qualification'
    acceptance=read_json(area/'operations-qualification.json')
    require(verify_envelope(acceptance,signer.public) and
            acceptance['scope_review_status']=='accepted-condition-satisfied','Reference review unresolved')
    replay=read_json(root/'work/ms93/isolated-control-reassessment.json')
    require(verify_envelope(replay,signer.public) and replay['status']=='passed-bounded-controls',
            'Isolated control reassessment missing')
    for folder in sorted((root/'work/ms93').iterdir()):
        if not folder.is_dir() or not folder.name.startswith(('reference-','negative-')):continue
        receipt=read_json(folder/'receipt.json');run=root/read_json(folder/'run.json')['run_directory']
        plan=read_json(run/'plan.json');gate=read_json(run/'gate.json');cleanup=read_json(run/'cleanup.json')
        verify(plan);verify(gate)
        require(verify_envelope(receipt,signer.public) and receipt==read_json(run/'receipt.json'),'Receipt changed')
        require(verify_envelope(cleanup,signer.public) and cleanup['complete'],'Unverified cleanup')
        require(receipt['plan_sha256']==plan['content_sha256'] and receipt['gate_sha256']==gate['content_sha256'],
                'Receipt/gate binding changed')
        for relative,sha in plan['implementation_sha256'].items():
            require(file_hash(run/'qualification-source'/relative)==sha,'Archived qualification source changed')
        attempts.append({'output':folder.relative_to(root).as_posix(),'run_id':run.name,
            'scenario':receipt['scenario'],'fault':receipt['fault'],'status':receipt['status'],
            'qualification_check_passed':receipt['qualification_check_passed'],
            'receipt_sha256':receipt['content_sha256'],'gate_sha256':gate['content_sha256'],
            'judge_version':receipt['judge_version'],'cleanup_verified':True,
            'elapsed_seconds':receipt['elapsed_seconds'],'builder_analyst_calls':receipt['model_calls'],
            'autonomous_success':receipt['autonomous_success']})
    require(len(attempts)==9 and all(not x['autonomous_success'] for x in attempts),'Unexpected equipment inventory')
    value=signer.sign({'artifact_type':'judge-environment-qualification-development-status',
        'status':'bounded-reference-qualified-development-gates-remain',
        'operations_scope_review':'accepted-condition-satisfied',
        'scope_acceptance_summary_sha256':acceptance['content_sha256'],
        'isolated_reassessment_sha256':replay['content_sha256'],'attempts':attempts,
        'attempt_status_counts':dict(Counter(x['status'] for x in attempts)),
        'summed_attempt_elapsed_seconds':round(sum(x['elapsed_seconds'] for x in attempts),3),
        'builder_analyst_calls':sum(x['builder_analyst_calls'] for x in attempts),
        'autonomous_success_count':0,'factory_success_rate':None,
        'remaining_release_gates':[
            'Separate component/stage checks and review of purchasing and support reference sources.',
            'Controller integration of controlled public MCP tools, with a new frozen implementation.',
            'Complete independently established footprint and declared trace-type feedback.',
            'Concrete pilot declaration, new source/call authorization, then pilot and ten fresh generations.',
            'Reserve unfamiliar evaluation scenarios separately from MS92 development regressions.'],
        'limits':['The four business-failure controls are expected rejections, not successful application runs.',
                  'The two failed equipment attempts remain in their original structured results.',
                  'Conditional acceptance applies to original operations scope, not line-by-line review of later source.',
                  'Summed attempt time includes preparation and cleanup; it is not CPU time or a dollar bill.']})
    save(area/'isolated-qualification.json',replay)
    save(area/'qualification-status.json',value);return value


if __name__=='__main__':
    value=report(Path('.'));print(json.dumps({k:value[k] for k in
        ('status','attempt_status_counts','summed_attempt_elapsed_seconds','builder_analyst_calls')}))
