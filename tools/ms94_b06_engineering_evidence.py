"""Public-key authentication for engineering handoff and consumed attempts."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_engineering import LABEL, require, sha
from tools.ms94_b06_engineering_key import check_identity


def binding(run, approval):
    run=Path(run);record=read_json(run/'engineering.json');verify(record)
    number=record.get('run_number')
    require(type(number) is int and number in (1,2),'receipt-attempt-number')
    require(run.parent==Path(approval['output_root'])/approval['content_sha256']/'runs' and
            record.get('owner')==run.name and record.get('approval_sha256')==approval['content_sha256'] and
            record.get('mode')==approval['attempt_modes'][number-1] and
            record.get('source_commit')==approval.get('implementation_commit',record.get('source_commit')) and
            record.get('runtime_source_commit')==approval['observer_source'] and
            record.get('engineering_key_sha256')==approval['engineering_key_sha256'] and
            all(record.get(k)==v for k,v in LABEL.items()),'receipt-attempt-binding')
    plan=read_json(run/'plan.json');verify(plan)
    return dict(owner=run.name,approval_sha256=approval['content_sha256'],run_number=number,
                mode=record['mode'],source_commit=record['source_commit'],
                engineering_key_sha256=approval['engineering_key_sha256'],
                engineering_record_sha256=record['content_sha256'],plan_sha256=plan['content_sha256'])


def signed(path, public, expected, approval):
    check_identity(public,approval['engineering_key_sha256'])
    value=read_json(path)
    require(verify_envelope(value,public),'receipt-signature')
    require(all(value.get(k)==v for k,v in {**LABEL,**expected}.items()),'receipt-binding')
    return value


def verify_handoff(run, assets, approval, public):
    run=Path(run);expected=binding(run,approval)
    return signed(run/'supervisor-handoff.json',public,dict(**expected,
        artifact_type='b06-engineering-handoff/1',assets_root=str(Path(assets).resolve()),
        template_path='templates/j1/plan.json',asset_index_sha256=approval.get('asset_index_sha256'),
        native_template_sha256=approval.get('native_template_sha256')),approval)


def verify_prior(run, approval, public):
    run=Path(run)
    require((run/'terminal.json').is_file() and (run/'artifacts.json').is_file(),'prior-run-unsealed')
    require(public is not None,'prior-public-key-required')
    expected=binding(run,approval)
    terminal=signed(run/'terminal.json',public,expected,approval)
    require(terminal.get('cleanup_verified') is True,'prior-cleanup-incomplete')
    cleanup_name=terminal.get('cleanup_record')
    require(cleanup_name in ('cleanup.json','supervisor-cleanup.json'),'prior-cleanup-record')
    cleanup=signed(run/cleanup_name,public,expected,approval)
    require(cleanup.get('complete') is True and cleanup.get('actual_absence_verified') is True and
            sha(run/cleanup_name)==terminal.get('cleanup_record_sha256'),'prior-cleanup-binding')
    artifacts=signed(run/'artifacts.json',public,dict(**expected,artifact_type='b06-engineering-artifacts/1'),approval)
    rows=artifacts.get('artifacts');require(isinstance(rows,list),'prior-artifacts-shape')
    names=set()
    for row in rows:
        name=row.get('path');p=Path(name) if isinstance(name,str) else Path('..')
        require(not p.is_absolute() and bool(p.parts) and not any(x in ('.','..') for x in p.parts) and
                p.as_posix()==name and name not in names and name!='artifacts.json','prior-artifact-path')
        names.add(name);path=run/p
        require(path.is_file() and not any(x.is_symlink() for x in (path,*path.parents)) and
                all(row.get(k)==v for k,v in LABEL.items()) and path.stat().st_size==row.get('bytes') and
                sha(path)==row.get('sha256'),'prior-artifact-changed')
    require(names=={p.relative_to(run).as_posix() for p in run.rglob('*') if p.is_file() and p!=run/'artifacts.json'},'prior-artifact-inventory')
    require({'engineering.json','plan.json','terminal.json',cleanup_name,'supervisor-handoff.json'}<=names,'prior-artifacts-incomplete')
    handoff=read_json(run/'supervisor-handoff.json')
    verify_handoff(run,handoff.get('assets_root',''),approval,public)
    return expected
