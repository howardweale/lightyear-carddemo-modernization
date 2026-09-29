"""Admit the exact unchanged base plus the freshly qualified invoice-type delta."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_stage_b_evidence import stage_a as base_stage_a
from tools.ms94_snapshot_v5 import EXTENSION
from tools.ms94_equipment_v5 import SCHEDULE
from tools.ms94_v5_gate import VERSION


def stage_a(root,equipment,live=False):
    root=Path(root);base,acceptance=base_stage_a(root,equipment,live=live)
    directory=root/EXTENSION;plan=read_json(directory/'plan.json');verify(plan)
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    report=read_json(directory/'report.json');auth=read_json(directory/'authorization.json')
    require(plan['base_equipment_plan_sha256']==base['content_sha256'] and plan['judge_version']==VERSION
            and plan['schedule']==SCHEDULE and plan['model_calls']==0,'Qualification delta differs')
    require(verify_envelope(report,key) and report['passed'] and report['plan_sha256']==plan['content_sha256']
            and report['unstarted_slots']==0 and report['error'] is None,'Invoice-type qualification incomplete')
    require(verify_envelope(auth,key) and auth['plan_sha256']==plan['content_sha256'] and auth['explicit_user_authorization'],
            'Qualification authorization differs')
    for name,digest in plan['implementation_sha256'].items():
        require(file_hash(root/name)==digest,'Qualified extension changed: '+name)
    require([x['profile'] for x in report['results']]==SCHEDULE,'Qualification results incomplete')
    for i,item in enumerate(report['results'],1):
        require(item['qualification_check_passed'] and item['cleanup_complete'] and item['publication_verified'],
                'Qualification outcome failed')
        receipt=read_json(directory/'publications'/f'{i:02d}'/'receipt.json')
        check=read_json(directory/'publications'/f'{i:02d}'/'verification.json')
        require(verify_envelope(receipt,key) and receipt['content_sha256']==item['publication_receipt_sha256'],
                'Qualification publication receipt differs')
        require(verify_envelope(check,key) and check['verified'] and check['complete_gate_replayed']
                and check['status']==item['status'] and check['run_id']==Path(item['run_directory']).name,
                'Qualification publication replay differs')
    return base,acceptance
