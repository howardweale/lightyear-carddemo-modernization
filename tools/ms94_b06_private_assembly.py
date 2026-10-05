"""Seal exact private per-slot inputs without starting a native or builder process."""
from pathlib import Path
import hashlib
import json
from lightyear_calibration.contracts import canonical, seal, verify
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_admission import check, bound_file
from lightyear_control_tower.status_export import atomic_new


def required(journey):
    shared={'operations.java','checkpoint.json','primary-keys.json','comparison-register.json',
            'datatype-inventory.json','oracle-entry-multisets.json','postgresql-entry-multisets.json'}
    if journey=='J1':return shared|{'invoice-type-contract.json','history-bound.json'}
    if journey=='J2':return shared|{'private-expectations.json','history-bound.json'}
    check(journey=='J3','private-assembly-journey')
    return shared|{'private-expectations.json','private-work-order.json','private-selection.json'}


def seal_inputs(destination, journey, schedule, inputs_by_slot):
    destination=Path(destination).resolve()
    check('work/ms94' not in destination.as_posix().lower(),'private-assembly-protected-path')
    ids=[s['id'] for s in schedule]
    check(ids and len(set(ids))==len(ids) and set(ids)==set(inputs_by_slot),'private-assembly-slots')
    check(all(Path(i).name==i and i not in ('.','..') for i in ids),'private-assembly-slot-path')
    check(not destination.exists(),'private-assembly-no-replacement')
    rows={}
    # Validate the entire assembly before writing any copies.
    for slot in schedule:
        files=inputs_by_slot[slot['id']]
        check(required(journey)<=set(files),'private-assembly-incomplete')
        check(all(Path(n).name==n and n not in ('.','..') for n in files),'private-assembly-name')
        check(all(isinstance(b,bytes) for b in files.values()),'private-assembly-bytes')
        hashes={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
        check(hashes['operations.java']==slot['source']['sha256'],'private-assembly-source')
        verify(json.loads(files['checkpoint.json']))
        if journey!='J1':check(json.loads(files['private-expectations.json'])['journey']==journey,'private-assembly-contract')
        rows[slot['id']]={'inputs_sha256':hashes,'control':slot['control']}
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'blobs').mkdir()
    for slot in schedule:
        for name,raw in inputs_by_slot[slot['id']].items():
            blob=destination/'blobs'/rows[slot['id']]['inputs_sha256'][name]
            if not blob.exists():
                with blob.open('xb') as stream:stream.write(raw)
    record=seal({'artifact_type':'ms94-b06-private-input-assembly/1','journey':journey,'slots':rows,
                 'native_pairs':0,'model_calls':0,'private_values_published':False})
    atomic_new(destination/'manifest.json',record)
    verify_assembly(destination,record)
    return record


def verify_assembly(root,record):
    verify(record)
    for slot,row in record['slots'].items():
        check(Path(slot).name==slot,'private-assembly-slot-path')
        check(required(record['journey'])<=set(row['inputs_sha256']),'private-assembly-incomplete')
        for name,sha in row['inputs_sha256'].items():
            check(Path(name).name==name,'private-assembly-input-path')
            bound_file(root,'blobs/'+sha,sha)
    return True
