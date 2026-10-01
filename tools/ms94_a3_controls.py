"""Unchanged revised A2 faults plus a retained-reference checkpoint-path check."""
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify,seal
from lightyear_calibration.journey_order import file_hash
from tools.ms94_diagnostic_controls_v7 import FAULTS,AREA,assess as fault_assess

CONTROLS=('retained-reference',*FAULTS)


def control(root,name):
    require(name in CONTROLS,'Unknown A3 control')
    if name=='retained-reference':
        source=Path(root)/'factory/idempiere/qualification-ms94-v5/references/retained/LightyearOperationsTest.java'
        prior=read_json(source.parent/'manifest.json');verify(prior)
        require(file_hash(source)==prior['harness_sha256'],'Retained A1 reference changed')
        manifest=seal({'artifact_type':'ms94-a3-retained-path-control','fault':name,
            'harness_sha256':prior['harness_sha256'],'test_only_support_change':False,
            'expected':{'status':'passed','equipment_suspect':False},
            'qualification_only':True,'model_calls':0,'autonomous_success':False})
    else:
        source=Path(root)/AREA/name/'LightyearOperationsTest.java'
        manifest=read_json(source.parent/'manifest.json');verify(manifest)
        require(file_hash(source)==manifest['harness_sha256'],'Revised A2 fault source changed')
    return source,manifest


def assess(gate,diagnostics,suspect,manifest):
    if manifest['fault']=='retained-reference':return gate['status']=='passed' and diagnostics==[] and suspect is False
    return fault_assess(gate,diagnostics,suspect,manifest)


def equal_projections(left,right):
    from lightyear_calibration.contracts import canonical
    # Compare actual exported bytes, not just a status or a declared hash.
    return (canonical(left['diagnostics'])==canonical(right['diagnostics'])
            and left['equipment_suspect']==right['equipment_suspect']
            and left['disposition']==right['disposition'])
