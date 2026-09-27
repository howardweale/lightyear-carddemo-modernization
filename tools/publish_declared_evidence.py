"""Lossless MS90 captures: replay original native gates and versioned comparison.

The archive contains observations, not database filesystems or credentials.
Signature verification requires the separately trusted public-key fingerprint.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from lightyear_calibration.contracts import canonical, read_json, require
from lightyear_calibration.journey_order import RUNS, file_hash, save
from lightyear_calibration.journey_runtime import JourneySigner, CONTROL
from lightyear_control_tower.decisions import verify_envelope
from tools.publish_native_journeys import (encode_blob, decode_blob, split_json_observation,
                                           safe_relative, matches_implementation)
from tools.evaluate_journey_judge_v2 import (source_files, verify_assessment, native_context,
                                           shipment_bindings)


def publish(root, assessment, output):
    root=root.resolve();assessment=assessment.resolve();output=output.resolve()
    require(not output.exists() and output.is_relative_to(root), 'Use a new publication directory')
    verify_assessment(assessment)
    signer=JourneySigner(root)
    require((assessment/'authority.public.pem').read_bytes()==signer.public, 'Assessment authority differs')
    plan=read_json(assessment/'plan.json');run=root/plan['source_directory']
    require(source_files(run)==plan['source_files'], 'Original source capture changed')
    files={};blobs={}
    def put(data):
        identity=hashlib.sha256(data).hexdigest();blobs.setdefault(identity,data);return identity
    sources=[(p,'native/'+p.relative_to(run).as_posix()) for p in (run/name for name in plan['source_files'])]
    sources += [(p,'assessment/'+p.name) for p in assessment.iterdir() if p.is_file()]
    for p,relative in sources:
        safe_relative(relative);require(not p.is_symlink(), 'Symbolic capture')
        raw=p.read_bytes()
        if p.name in ('state.json','catalog.json'): stored,encoding=split_json_observation(raw,put)
        else: stored,encoding=encode_blob(raw)
        identity=put(stored)
        files[relative]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'blob_sha256':identity,**encoding}
    manifest=signer.sign({'artifact_type':'lightyear-complete-reassessment-captures','version':'1',
        'run_id':run.name,'files':files,'assessment_receipt_sha256':read_json(assessment/'receipt.json')['content_sha256'],
        'implementation_sha256':plan['implementation_sha256'],
        'original_gate_passed':False,'assessment_kind':'retained-native-evidence-reassessment',
        'authority_sha256':hashlib.sha256(signer.public).hexdigest(),'independently_attested':False})
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr('manifest.json',canonical(manifest))
        archive.writestr('authority.public.pem',signer.public)
        for key,data in sorted(blobs.items()):archive.writestr('blobs/'+key,data)
    receipt=signer.sign({'artifact_type':'lightyear-complete-reassessment-publication',
        'manifest_sha256':manifest['content_sha256'],'archive_sha256':file_hash(output/'evidence.zip'),
        'authority_sha256':manifest['authority_sha256'],'run_id':run.name,'file_count':len(files),
        'archive_bytes':(output/'evidence.zip').stat().st_size,'new_native_executions':0,
        'new_model_calls':0,'independently_attested':False})
    save(output/'receipt.json',receipt);(output/'authority.public.pem').write_bytes(signer.public)
    return receipt


def verify_publication(root, publication, trusted_key_sha256, temporary_parent=None):
    key=(publication/'authority.public.pem').read_bytes()
    require(hashlib.sha256(key).hexdigest()==trusted_key_sha256,'Publication key is not the trusted operator key')
    receipt=read_json(publication/'receipt.json')
    require(verify_envelope(receipt,key) and receipt['authority_sha256']==trusted_key_sha256,'Publication signature differs')
    require(file_hash(publication/'evidence.zip')==receipt['archive_sha256'],'Archive changed')
    with zipfile.ZipFile(publication/'evidence.zip') as archive, tempfile.TemporaryDirectory(dir=temporary_parent) as temp:
        stage=Path(temp);manifest=json.loads(archive.read('manifest.json'))
        require(verify_envelope(manifest,key) and manifest['content_sha256']==receipt['manifest_sha256'],'Manifest differs')
        require(manifest['authority_sha256']==trusted_key_sha256 and archive.read('authority.public.pem')==key,'Archive key differs')
        require(manifest['run_id']==receipt['run_id'] and manifest['run_id'].startswith('journey-'),'Run identity differs')
        safe_relative(manifest['run_id']);require('/' not in manifest['run_id'],'Unsafe run identity')
        for relative,expected in manifest['implementation_sha256'].items():
            p=safe_relative(relative)
            require(matches_implementation(root/Path(*p.parts),expected),'Use the implementation pinned by the original assessment: '+relative)
        expected={'manifest.json','authority.public.pem'}
        for record in manifest['files'].values():
            expected.add('blobs/'+record['blob_sha256'])
            expected.update('blobs/'+c['blob_sha256'] for c in record.get('components',[]))
        names=archive.namelist()
        require(len(names)==len(set(names)) and set(names)==expected,'Unexpected/duplicate archive member')
        require(sum(info.file_size for info in archive.infolist())<4*1024**3,'Oversized evidence archive')
        run=stage/RUNS/manifest['run_id'];assessment=stage/'assessment'
        for relative,record in manifest['files'].items():
            p=safe_relative(relative)
            require(p.parts[0] in ('native','assessment') and len(p.parts)>1,'Invalid evidence scope')
            target=(run if p.parts[0]=='native' else assessment)/Path(*p.parts[1:])
            raw=decode_blob(archive.read('blobs/'+record['blob_sha256']),record,
                            lambda h:archive.read('blobs/'+h))
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        trust=stage/CONTROL/'authority.public.pem';trust.parent.mkdir(parents=True);trust.write_bytes(key)
        verify_assessment(assessment)
        require(read_json(assessment/'receipt.json')['content_sha256']==manifest['assessment_receipt_sha256'],'Assessment differs')
        plan=read_json(assessment/'plan.json')
        require(source_files(run)==plan['source_files'],'Reconstructed full capture differs')
        from lightyear_calibration.partial_invoicing import verify_run
        from lightyear_calibration.journey_judge_v2 import compare
        old=verify_run(run)
        require(old==read_json(assessment/'original-gate.json'),'Complete native gate replay differs')
        attempt=read_json(run/'selected-attempts.json')['partial-invoicing']
        folder=run/'cases/partial-invoicing'/str(attempt)
        lanes={lane:read_json(folder/'verified'/(lane+'.json')) for lane in ('oracle','postgresql')}
        context,snapshots=native_context(folder)
        result=compare(lanes,read_json(folder/'verified/effects.json'),old['comparison'],
            shipment_bindings(folder,lanes,snapshots),context,read_json(assessment/'policy.json'),
            read_json(assessment/'timestamp-decision.json'),date.fromisoformat(plan['assessed_on']))
        require(result==read_json(assessment/'comparison-v2.json'),'Recomputed versioned verdict differs')
        return {'status':'verified-complete-native-captures','original_gate_passed':old['passed'],
            'versioned_comparison_passed':result['passed'],'judge_version':result['judge_version'],
            'full_native_gate_replayed':True,'new_native_executions':0,'independently_attested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['publish','verify'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--assessment',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--trusted-key-sha256')
    p.add_argument('--temporary-parent',type=Path)
    a=p.parse_args()
    value=publish(a.root,a.assessment,a.output) if a.command=='publish' else verify_publication(
        a.root,a.output,a.trusted_key_sha256,a.temporary_parent)
    print(json.dumps(value,indent=2))


if __name__=='__main__':main()
