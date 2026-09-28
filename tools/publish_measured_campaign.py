"""Lossless, signed MS92 campaign publication and offline native-judge replay."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from lightyear_calibration.contracts import canonical, read_json, require
from lightyear_calibration.journey_order import file_hash, save, RUNS
from lightyear_calibration.journey_runtime import JourneySigner, CONTROL
from lightyear_control_tower.decisions import verify_envelope
from tools.publish_native_journeys import encode_blob, decode_blob, split_json_observation, safe_relative, matches_implementation


def publish(root,campaign,output):
    from lightyear_calibration.measured_campaign import audit
    root=root.resolve();campaign=campaign.resolve();output=output.resolve()
    require(campaign.is_relative_to(root) and output.is_relative_to(root) and not output.exists(), 'Use a new workspace publication')
    signer=JourneySigner(root);result=read_json(campaign/'receipt.json');plan=read_json(campaign/'plan.json')
    require(verify_envelope(result,signer.public) and result['plan_sha256']==plan['content_sha256'],'Campaign receipt differs')
    require(audit(root,campaign,result['attempts'])==result['provenance'],'Campaign provenance differs')
    paths=[p for p in campaign.rglob('*') if p.is_file()]
    for attempt in result['attempts']:
        relative=safe_relative(attempt['run_directory']);run=root/Path(*relative.parts)
        require(run.parent==root/RUNS,'Unexpected native run directory')
        paths.extend(p for p in run.rglob('*') if p.is_file() and 'journal' not in p.relative_to(run).parts
                     and p.name not in ('active-resources.json',))
    # Public inputs and implementation travel with the exact signed declaration.
    paths.extend(root/name for name in plan['implementation_sha256'])
    files={};blobs={}
    def put(data):
        h=hashlib.sha256(data).hexdigest();blobs.setdefault(h,data);return h
    for path in sorted(set(paths)):
        require(not path.is_symlink() and path.is_relative_to(root),'Symbolic/outside campaign artifact')
        require('key.pem' not in path.name and path.suffix not in ('.db','.sqlite','.sqlite3'),'Private/live file in publication')
        raw=path.read_bytes();name=path.relative_to(root).as_posix();safe_relative(name)
        if path.name in ('state.json','catalog.json'):stored,encoding=split_json_observation(raw,put)
        else:stored,encoding=encode_blob(raw)
        files[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'blob_sha256':put(stored),**encoding}
    manifest=signer.sign({'artifact_type':'lightyear-complete-frozen-campaign','version':'1',
        'campaign_directory':campaign.relative_to(root).as_posix(),'files':files,
        'campaign_receipt_sha256':result['content_sha256'],'plan_sha256':plan['content_sha256'],
        'implementation_sha256':plan['implementation_sha256'],'authority_sha256':hashlib.sha256(signer.public).hexdigest()})
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr('manifest.json',canonical(manifest))
        for h,data in sorted(blobs.items()):archive.writestr('blobs/'+h,data)
    receipt=signer.sign({'artifact_type':'lightyear-complete-frozen-campaign-publication',
        'manifest_sha256':manifest['content_sha256'],'archive_sha256':file_hash(output/'evidence.zip'),
        'file_count':len(files),'archive_bytes':(output/'evidence.zip').stat().st_size,
        'authority_sha256':manifest['authority_sha256'],'independently_attested':False})
    save(output/'receipt.json',receipt);(output/'authority.public.pem').write_bytes(signer.public);return receipt


def verify_publication(root,publication,trusted_key_sha256,temporary_parent=None):
    from lightyear_calibration.measured_judge import verify_run
    from lightyear_calibration.measured_campaign import audit
    key=(publication/'authority.public.pem').read_bytes();receipt=read_json(publication/'receipt.json')
    require(hashlib.sha256(key).hexdigest()==trusted_key_sha256 and verify_envelope(receipt,key),'Untrusted publication key/signature')
    require(file_hash(publication/'evidence.zip')==receipt['archive_sha256'],'Archive changed')
    with zipfile.ZipFile(publication/'evidence.zip') as archive,tempfile.TemporaryDirectory(dir=temporary_parent) as temporary:
        stage=Path(temporary);manifest=json.loads(archive.read('manifest.json'))
        require(verify_envelope(manifest,key) and manifest['content_sha256']==receipt['manifest_sha256'],'Manifest differs')
        require(manifest['authority_sha256']==trusted_key_sha256,'Manifest authority differs')
        expected={'manifest.json'}
        for record in manifest['files'].values():
            expected.add('blobs/'+record['blob_sha256'])
            expected.update('blobs/'+c['blob_sha256'] for c in record.get('components',[]))
        require(len(archive.namelist())==len(expected) and set(archive.namelist())==expected,'Unexpected/duplicate archive file')
        require(sum(i.file_size for i in archive.infolist())<8*1024**3,'Oversized campaign archive')
        for relative,record in manifest['files'].items():
            path=stage/Path(*safe_relative(relative).parts)
            require(path.is_relative_to(stage),'Escaping archive member')
            raw=decode_blob(archive.read('blobs/'+record['blob_sha256']),record,lambda h:archive.read('blobs/'+h))
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        for relative,expected_hash in manifest['implementation_sha256'].items():
            relative=Path(*safe_relative(relative).parts)
            require(matches_implementation(root/relative,expected_hash) and file_hash(stage/relative)==expected_hash,
                    'Replay requires the frozen implementation: '+str(relative))
        trust=stage/CONTROL/'authority.public.pem';trust.parent.mkdir(parents=True,exist_ok=True);trust.write_bytes(key)
        campaign=stage/Path(*safe_relative(manifest['campaign_directory']).parts)
        result=read_json(campaign/'receipt.json')
        require(verify_envelope(result,key) and result['content_sha256']==manifest['campaign_receipt_sha256'],'Campaign receipt differs')
        require(audit(stage,campaign,result['attempts'])==result['provenance'],'Offline source/repair provenance differs')
        replayed=[]
        for attempt in result['attempts']:
            run=stage/Path(*safe_relative(attempt['run_directory']).parts)
            require(run.parent==stage/RUNS,'Invalid native attempt path')
            native=read_json(run/'receipt.json')
            require(verify_envelope(native,key) and native['content_sha256']==attempt['receipt_sha256'],'Native receipt differs')
            if (run/'gate.json').exists():
                recorded=read_json(run/'gate.json');actual=verify_run(run)
                require(actual==recorded,'Full native judge replay differs')
                replayed.append({'run_id':run.name,'gate_replayed':True,'passed':actual['passed']})
            else:
                require(not attempt['passed'],'Passing attempt has no native gate')
                replayed.append({'run_id':run.name,'gate_replayed':False,'passed':False,
                                 'reason':'Execution failed before a complete paired capture/gate existed'})
        return {'status':'verified-complete-frozen-campaign','judge_version':result['judge_version'],
                'attempts':replayed,'dark_factory_run':result['dark_factory_run'],
                'new_native_executions':0,'new_model_calls':0,'independently_attested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['publish','verify'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--campaign',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--trusted-key-sha256');p.add_argument('--temporary-parent',type=Path)
    a=p.parse_args()
    result=publish(a.root,a.campaign,a.output) if a.command=='publish' else verify_publication(a.root,a.output,a.trusted_key_sha256,a.temporary_parent)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
