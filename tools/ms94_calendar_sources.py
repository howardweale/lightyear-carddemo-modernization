"""New date-valued qualification sources; inherited sources stay immutable."""
from pathlib import Path
import hashlib
from lightyear_calibration.contracts import canonical, read_json, require, seal, verify
from lightyear_calibration.journey_order import file_hash, save
from tools.ms94_calendar import derive, render, projection
from tools.ms94_dated_controls import dated
from tools.ms94_diagnostic_controls_v7 import FAULTS, construct

AREA=Path('factory/idempiere/qualification-ms94-v11/calendar')

def prepare(root):
    root=Path(root);out=root/AREA;require(not out.exists(),'Never replace frozen calendar inputs')
    calendar=derive();out.mkdir(parents=True)
    from tools.ms94_controller_v5 import public_prompt
    original=canonical(public_prompt(root));rendered=render(original,calendar)
    (out/'builder-prompt.json').write_bytes(rendered)
    # Embedded B03 source content hashes remain byte-identical provenance labels.
    # The new complete payload is bound by the separate prospective plan hash.
    audit=projection(original,rendered,calendar)
    manifests={}
    for profile in ('retained','equivalent','alternate'):
        prior=root/'factory/idempiere/qualification-ms94-v5/references'/profile/'LightyearOperationsTest.java'
        old=read_json(prior.parent/'manifest.json');require(file_hash(prior)==old['harness_sha256'],'Prior source differs')
        explicit=dated(prior.read_text(encoding='utf-8')).encode('utf-8')
        if profile=='retained':
            expected=(root/'factory/idempiere/qualification-ms94-v8/dated-controls/retained-reference/LightyearOperationsTest.java').read_bytes()
            require(explicit==expected,'Retained differs from qualified dated reference')
        raw=render(explicit,calendar);folder=out/'references'/profile;folder.mkdir(parents=True)
        (folder/'LightyearOperationsTest.java').write_bytes(raw)
        manifest=seal({**{k:v for k,v in old.items() if k!='content_sha256'},
            'harness_sha256':hashlib.sha256(raw).hexdigest(),'calendar_sha256':calendar['content_sha256'],
            'prior_source':prior.relative_to(root).as_posix(),'prior_source_sha256':file_hash(prior),
            'source_change':'Explicit order DateAcct plus calendar date substitution; no other source changes.',
            'date_projection':projection(explicit,raw,calendar),'prior_qualification_credit':False})
        save(folder/'manifest.json',manifest);manifests[profile]=manifest
        if profile=='retained':retained=raw.decode('utf-8')
    for fault in FAULTS:
        raw,expected=construct(retained,fault);folder=out/'controls'/fault;folder.mkdir(parents=True)
        (folder/'LightyearOperationsTest.java').write_bytes(raw.encode('utf-8'))
        prior=root/'factory/idempiere/qualification-ms94-v8/dated-controls'/fault/'LightyearOperationsTest.java'
        require(render(prior.read_bytes(),calendar)==raw.encode('utf-8'),'Dated fault changed beyond dates')
        manifest=seal({'fault':fault,'harness_sha256':file_hash(folder/'LightyearOperationsTest.java'),
            'expected':expected,'test_only_support_change':fault=='support-throw',
            'calendar_sha256':calendar['content_sha256'],'prior_source':prior.relative_to(root).as_posix(),
            'prior_source_sha256':file_hash(prior),'date_projection':projection(prior.read_bytes(),raw.encode('utf-8'),calendar),
            'prior_qualification_credit':False,'model_calls':0})
        save(folder/'manifest.json',manifest);manifests[fault]=manifest
    save(out/'calendar.json',calendar)
    save(out/'inputs-audit.json',seal({'calendar_sha256':calendar['content_sha256'],'builder_prompt':audit,
        'embedded_b03_content_hashes':'Preserved source provenance labels; the transformed payload has a new independently declared digest.',
        'sources':{k:v['content_sha256'] for k,v in manifests.items()},'model_calls':0}))
    return calendar

def source(root,profile,delivery_fault=None):
    path=Path(root)/AREA/('controls' if delivery_fault else 'references')/(delivery_fault or profile)/'LightyearOperationsTest.java'
    manifest=read_json(path.parent/'manifest.json');verify(manifest)
    require(file_hash(path)==manifest['harness_sha256'],'Calendar source changed')
    return path,manifest
