"""Lossless full native captures, signed inventory, independently replayable gates.

Reference source and private results are evidence, never builder inputs. Operator
private keys, live journals and raw application staging are not published.
"""
import hashlib,json,tempfile,zipfile
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require
from lightyear_calibration.journey_order import file_hash,save,RUNS
from lightyear_calibration.journey_runtime import CONTROL
from tools.ms94_signer_v5 import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools.publish_native_journeys import encode_blob,decode_blob,split_json_observation,safe_relative


def publish(root,run,output):
    require(not output.exists(),'Publication already exists')
    signer=JourneySigner(root);plan=read_json(run/'plan.json');receipt=read_json(run/'receipt.json')
    require(verify_envelope(receipt,signer.public),'Invalid native receipt')
    for name,expected in plan['implementation_sha256'].items():
        require(file_hash(root/name)==expected,'Cannot publish changed execution implementation')
    paths=[p for p in run.rglob('*') if p.is_file() and
           not set(p.relative_to(run).parts)&{'journal','application-output'} and p.name!='active-resources.json']
    paths += [root/p for p in plan['implementation_sha256']]
    campaign=root/Path(*safe_relative(plan['campaign_directory']).parts)
    cp=read_json(campaign/'plan.json')
    paths += [p for p in campaign.rglob('*') if p.is_file()]
    for attempt in read_json(campaign/'receipt.json')['attempts']:
        other=root/Path(*safe_relative(attempt['run_directory']).parts)
        require(other.parent==root/RUNS,'Unexpected trial native path')
        paths += [p for p in other.rglob('*') if p.is_file() and
                  not set(p.relative_to(other).parts)&{'journal','application-output'} and p.name!='active-resources.json']
    equipment=root/Path(*safe_relative(cp['equipment_directory']).parts)
    paths += list(equipment.rglob('*.json'))
    blobs={};files={}
    def put(data):
        h=hashlib.sha256(data).hexdigest();blobs.setdefault(h,data);return h
    for path in sorted(set(paths)):
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),'Unsafe publication path')
        require('key.pem' not in path.name and path.suffix not in ('.db','.sqlite','.sqlite3'),'Private/live evidence file')
        raw=path.read_bytes();name=path.relative_to(root).as_posix();safe_relative(name)
        stored,encoding=split_json_observation(raw,put) if path.name in ('state.json','catalog.json') else encode_blob(raw)
        files[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'blob_sha256':put(stored),**encoding}
    manifest=signer.sign({'artifact_type':'ms94-full-native-publication','run_directory':run.relative_to(root).as_posix(),
        'files':files,'implementation_sha256':plan['implementation_sha256'],'campaign_directory':plan['campaign_directory'],
        'native_receipt_sha256':receipt['content_sha256'],'gate_sha256':read_json(run/'gate.json')['content_sha256'],
        'authority_sha256':hashlib.sha256(signer.public).hexdigest()})
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('manifest.json',canonical(manifest))
        for h,data in sorted(blobs.items()):z.writestr('blobs/'+h,data)
    value=signer.sign({'artifact_type':'ms94-full-native-publication-receipt','manifest_sha256':manifest['content_sha256'],
        'archive_sha256':file_hash(output/'evidence.zip'),'archive_bytes':(output/'evidence.zip').stat().st_size,
        'file_count':len(files),'authority_sha256':manifest['authority_sha256']})
    save(output/'receipt.json',value);(output/'authority.public.pem').write_bytes(signer.public)
    return value


def replay(root,publication,trusted_key_sha256,temporary_parent=None):
    from tools.ms94_v5_gate import evaluate
    key=(publication/'authority.public.pem').read_bytes();receipt=read_json(publication/'receipt.json')
    require(hashlib.sha256(key).hexdigest()==trusted_key_sha256 and verify_envelope(receipt,key),'Untrusted publication')
    require(file_hash(publication/'evidence.zip')==receipt['archive_sha256'],'Archive changed')
    with zipfile.ZipFile(publication/'evidence.zip') as z,tempfile.TemporaryDirectory(dir=temporary_parent) as temp:
        stage=Path(temp);m=json.loads(z.read('manifest.json'))
        require(verify_envelope(m,key) and m['content_sha256']==receipt['manifest_sha256'],'Manifest changed')
        expected={'manifest.json'}
        for r in m['files'].values():
            expected.add('blobs/'+r['blob_sha256']);expected.update('blobs/'+x['blob_sha256'] for x in r.get('components',[]))
        require(len(z.namelist())==len(expected) and set(z.namelist())==expected,'Unexpected archive member')
        require(sum(x.file_size for x in z.infolist())<8*1024**3,'Archive exceeds bound')
        for name,r in m['files'].items():
            p=stage/Path(*safe_relative(name).parts)
            data=decode_blob(z.read('blobs/'+r['blob_sha256']),r,lambda h:z.read('blobs/'+h))
            require(len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'],'Decoded evidence changed')
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        for name,sha in m['implementation_sha256'].items():
            require(file_hash(root/name)==sha and file_hash(stage/name)==sha,'Replay implementation changed: '+name)
        p=stage/CONTROL/'authority.public.pem';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(key)
        run=stage/Path(*safe_relative(m['run_directory']).parts)
        require(run.parent==stage/RUNS,'Unexpected native directory')
        native=read_json(run/'receipt.json');recorded=read_json(run/'gate.json')
        require(verify_envelope(native,key) and native['content_sha256']==m['native_receipt_sha256'],'Native receipt changed')
        actual=evaluate(run)
        require(actual==recorded and actual['content_sha256']==m['gate_sha256'],'Complete gate replay differs')
        from tools.ms94_controller_v5 import audit
        campaign=stage/Path(*safe_relative(m['campaign_directory']).parts)
        cr=read_json(campaign/'receipt.json')
        require(verify_envelope(cr,key),'Trial result signature changed')
        require(audit(stage,campaign,cr['attempts'])==cr['provenance'],'Tool-inclusive provenance replay differs')
        return {'verified':True,'run_id':run.name,'gate_sha256':actual['content_sha256'],
                'status':actual['status'],'complete_gate_replayed':True,'new_model_calls':0,'new_native_executions':0}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--publication',type=Path,required=True)
    p.add_argument('--trusted-key-sha256',required=True);p.add_argument('--temporary-parent',type=Path)
    a=p.parse_args();print(json.dumps(replay(a.root.resolve(),a.publication.resolve(),a.trusted_key_sha256,a.temporary_parent),indent=2))
