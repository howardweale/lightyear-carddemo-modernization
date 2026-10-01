"""New explicitly dated reference and faults; all previous sources are immutable."""
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,seal,verify
from lightyear_calibration.journey_order import file_hash,save
from tools.ms94_diagnostic_controls_v7 import BASE as OLD_BASE,AREA as OLD_AREA,FAULTS,construct
from tools.ms94_a3_controls import assess,equal_projections

AREA=Path('factory/idempiere/qualification-ms94-v8/dated-controls')
CONTROLS=('retained-reference',*FAULTS)
ANCHOR='            order.setDateOrdered(businessDate);'
ADDITION='            order.setDateAcct(businessDate);\n'


def dated(source):
    require(source.count(ANCHOR)==1 and 'order.setDateAcct(' not in source,'Unexpected reference dating')
    return source.replace(ANCHOR,ADDITION+ANCHOR,1)


def prepare(root):
    root=Path(root);old=root/OLD_BASE;original=old.read_text(encoding='utf-8')
    require(file_hash(old)==read_json(old.parent/'manifest.json')['harness_sha256'],'Original reference changed')
    reference=dated(original);results={}
    for name in CONTROLS:
        folder=root/AREA/name;require(not folder.exists(),'Never replace a control source')
        if name=='retained-reference':
            source=reference;expected={'status':'passed','equipment_suspect':False};prior=old
        else:
            source,expected=construct(reference,name);prior=root/OLD_AREA/name/'LightyearOperationsTest.java'
            require(source==dated(prior.read_text(encoding='utf-8')),'Control changed beyond explicit order date')
        folder.mkdir(parents=True);target=folder/'LightyearOperationsTest.java';target.write_bytes(source.encode('utf-8'))
        require(source.split('final class JourneySupport {',1)[1]==prior.read_text(encoding='utf-8').split('final class JourneySupport {',1)[1],
                'Control support changed')
        value=seal({'artifact_type':'ms94-explicit-order-date-control','fault':name,
            'base_reference_sha256':hashlib_sha(reference),'harness_sha256':file_hash(target),
            'prior_source':prior.relative_to(root).as_posix(),'prior_source_sha256':file_hash(prior),
            'expected':expected,'test_only_support_change':name=='support-throw',
            'human_source_attestation':False,'qualification_only':True,'autonomous_success':False,'model_calls':0,
            'revision':'explicit-order-accounting-date-v1','original_wait_only_control_pass_claim':False,
            'change':'One added order.setDateAcct(businessDate) before save; all other source bytes unchanged.',
            'prior_qualification_applies_to_this_source':False})
        save(folder/'manifest.json',value);results[name]=value
    return results


def hashlib_sha(text):
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def control(root,name):
    require(name in CONTROLS,'Unknown explicitly dated control')
    source=Path(root)/AREA/name/'LightyearOperationsTest.java';manifest=read_json(source.parent/'manifest.json');verify(manifest)
    require(file_hash(source)==manifest['harness_sha256'],'Explicitly dated source changed')
    prior=Path(root)/manifest['prior_source']
    require(file_hash(prior)==manifest['prior_source_sha256']
            and source.read_text(encoding='utf-8')==dated(prior.read_text(encoding='utf-8')),
            'Control source exceeds declared date correction')
    return source,manifest


if __name__=='__main__':prepare(Path('.').resolve())
