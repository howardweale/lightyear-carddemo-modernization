"""Publish replayable native observations without credentials or database exports.

The archive deduplicates identical row blobs. Verification needs no database,
container, model, private key or network. Signatures are local attribution,
not independent attestation. The public key must match the separately reviewed
publication receipt; a self-supplied replacement key cannot authenticate it.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from lightyear_calibration.contracts import canonical, read_json, require, verify
from lightyear_calibration.journey_order import RUNS, COMMANDS, file_hash, save
from lightyear_calibration.journey_runtime import JourneySigner, CONTROL
from lightyear_control_tower.decisions import verify_envelope
from lightyear_data.contracts import content_hash
from lightyear_workflow.campaign_journals import check

TOP_LEVEL=('plan.json','authorization.json','authority.public.pem','receipt.json',
           'cleanup.json','selected-attempts.json','journal.json')
TREES=('inputs','cases','gates')
BUILDER_FILES=('receipt.json','prompt.json','proposal.json','events.jsonl','invocation.json','workspace/LightyearPartialInvoiceTest.java')


def safe_relative(value):
    p=PurePosixPath(value)
    require(isinstance(value,str) and str(p)==value and not p.is_absolute()
            and '..' not in p.parts and '\\' not in value and ':' not in value,
            'Unsafe archive path')
    return p


def matches_implementation(path,expected):
    """Git checkout may convert Python line endings; no other edit is admitted."""
    raw=path.read_bytes()
    variants={raw}
    if path.suffix=='.py':
        lf=raw.replace(b'\r\n',b'\n');variants.update((lf,lf.replace(b'\n',b'\r\n')))
    return expected in {hashlib.sha256(value).hexdigest() for value in variants}


def business_projection(run):
    """Keep observed outcomes; omit only generated trace IDs and UUIDs."""
    selected=read_json(run/'selected-attempts.json');result={}
    for case in ('boundary','operations'):
        result[case]={}
        for lane in ('oracle','postgresql'):
            value=read_json(run/'cases'/case/str(selected[case])/'verified'/(lane+'.json'));verify(value)
            result[case][lane]={'checks':value.get('boundary_contract',value.get('business_checks')),
                'accounting_entries_verified':value['accounting_entries_verified'],
                'balanced_accounting_groups':value['balanced_accounting_groups'],
                'trace':{k:v for k,v in value['trace'].items() if not k.endswith(('.uuid','.id','Id'))}}
    return result


def encode_blob(data):
    # Python gzip embeds capture time even when the row bytes are unchanged.
    # Separate just those four header bytes; reconstruct the original exactly.
    if len(data)>=18 and data[:3]==b'\x1f\x8b\x08':
        return data[:4]+b'\0'*4+data[8:],{'encoding':'gzip-mtime-v1','gzip_mtime':data[4:8].hex()}
    return data,{'encoding':'identity'}


def split_json_observation(data,put):
    """Separate repeated catalog results and row multisets without changing JSON."""
    value=json.loads(data)
    render=lambda v:json.dumps(v,separators=(',',':'),ensure_ascii=True).encode('utf-8')
    require(render(value)==data,'Observation JSON is not exactly round-trippable')
    paths=[]
    if value.get('artifact_type')=='lightyear-native-state-observation':
        paths=[['tables',table,'row_multiset'] for table in value['tables']]
        paths.extend(['structure',kind] for kind in value['structure'])
    elif 'results' in value and value.get('evidence_class')=='native-catalog-observation':
        paths=[['results',kind] for kind in value['results']]
    else:return data,{'encoding':'identity'}
    components=[]
    for path in paths:
        parent=value
        for part in path[:-1]:parent=parent[part]
        blob=render(parent[path[-1]]);digest=put(blob);parent[path[-1]]=None
        components.append({'path':path,'blob_sha256':digest})
    return render(value),{'encoding':'json-components-v1','components':components}


def decode_blob(data,entry,load=None):
    require(hashlib.sha256(data).hexdigest()==entry['blob_sha256'],'Stored blob changed')
    if entry['encoding']=='gzip-mtime-v1':
        require(data[:3]==b'\x1f\x8b\x08' and data[4:8]==b'\0'*4,'Invalid gzip header encoding')
        stamp=bytes.fromhex(entry['gzip_mtime']);require(len(stamp)==4,'Invalid gzip timestamp')
        data=data[:4]+stamp+data[8:]
    elif entry['encoding']=='json-components-v1':
        require(load is not None,'JSON components require their verified blobs')
        value=json.loads(data)
        for component in entry['components']:
            path=component['path'];require(len(path) in (2,3) and all(isinstance(p,str) for p in path),'Invalid component path')
            parent=value
            for part in path[:-1]:parent=parent[part]
            require(parent[path[-1]] is None,'Overlapping JSON components')
            raw=load(component['blob_sha256'])
            require(hashlib.sha256(raw).hexdigest()==component['blob_sha256'],'JSON component changed')
            parent[path[-1]]=json.loads(raw)
        data=json.dumps(value,separators=(',',':'),ensure_ascii=True).encode('utf-8')
    else:require(entry['encoding']=='identity','Unknown blob encoding')
    require(len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],'Reconstructed evidence changed')
    return data


def verify_run_identity(run,key):
    auth=read_json(run/'authorization.json');receipt=read_json(run/'receipt.json')
    plan=read_json(run/'plan.json');verify(plan)
    require((run/'authority.public.pem').read_bytes()==key,'Run authority differs')
    require(verify_envelope(auth,key) and verify_envelope(receipt,key),'Invalid run signature')
    require(auth['run_id']==receipt['run_id']==run.name and auth['plan']['plan_sha256']==receipt['plan_sha256']==plan['content_sha256'],'Run scope differs')
    events=read_json(run/'journal.json');previous=None
    require(0<len(events)<=256,'Unbounded or empty exported journal')
    for index,event in enumerate(events,1):
        require(event['sequence']==index and event['previous_sha256']==previous
                and event['content_sha256']==content_hash(event),'Exported journal chain differs')
        previous=event['content_sha256']
    check(events,auth,key,'journey')
    require(events[-1]['type']=='halted','Missing terminal journal event')
    terminal=events[-1]['payload']
    require(all(terminal.get(k)==v for k,v in receipt.items() if k not in ('signature','content_sha256')),'Journal and terminal receipt disagree')
    return receipt


def publish(root,runs,output):
    require(not output.exists(),'Publication output already exists')
    signer=JourneySigner(root);receipts=[];files={};blobs={};modes=set()
    def put(data):
        digest=hashlib.sha256(data).hexdigest();blobs.setdefault(digest,data);return digest
    for run in runs:
        require(run.parent==root/RUNS,'Only local native journey runs can be published')
        receipt=verify_run_identity(run,signer.public)
        plan=read_json(run/'plan.json');mode=plan.get('mode','replay');modes.add(mode)
        require(receipt['error'] is None,'Native run contains an error')
        if mode=='replay':
            require(receipt['unattended_run'] and receipt['known_findings_reproduced'] and receipt['bounded_operations_equivalence'],'Replay did not meet acceptance')
        else:
            require(mode=='extend' and receipt['agent_generated'] and receipt['unattended_extension'] and receipt['bounded_partial_invoicing_equivalence'],'Extension did not meet acceptance')
        cleanup=read_json(run/'cleanup.json')
        require(verify_envelope(cleanup,signer.public) and cleanup['complete'] and cleanup['content_sha256']==receipt['cleanup_sha256'],'Cleanup not verified')
        paths=[run/name for name in TOP_LEVEL]
        for name in TREES:paths.extend(sorted(p for p in (run/name).rglob('*') if p.is_file()))
        if mode=='extend':
            directory=safe_relative(plan['builder_directory'])
            require(directory.parts[:2]==('work','ms88') and len(directory.parts)==3 and directory.name.startswith('build-'),'Unexpected builder directory')
            paths.extend(root/Path(*directory.parts)/name for name in BUILDER_FILES)
            paths.append(run/'gate.json')
        for path in paths:
            require(not path.is_symlink(),'Symbolic evidence path')
            relative=path.relative_to(root).as_posix();safe_relative(relative)
            data=path.read_bytes()
            if path.name in ('state.json','catalog.json'):
                stored,encoding=split_json_observation(data,put)
            else:stored,encoding=encode_blob(data)
            digest=hashlib.sha256(data).hexdigest();blob_digest=hashlib.sha256(stored).hexdigest()
            files[relative]={'sha256':digest,'blob_sha256':blob_digest,'bytes':len(data),**encoding}
            blobs.setdefault(blob_digest,stored if encoding['encoding']=='json-components-v1' else path)
        receipts.append({'run_id':run.name,'receipt_sha256':receipt['content_sha256'],
                         'plan_sha256':receipt['plan_sha256'],'declaration_sha256':receipt['declaration_sha256']})
    require(len(modes)==1,'Do not mix replay and extension publications')
    mode=next(iter(modes));expected_count=2 if mode=='replay' else 1
    require(len(receipts)==expected_count and len({r['run_id'] for r in receipts})==expected_count,'Unexpected acceptance run count')
    require(len({r['plan_sha256'] for r in receipts})==len({r['declaration_sha256'] for r in receipts})==1,'Acceptance replays differ in plan or declaration')
    approval=None
    outcomes=None
    if mode=='replay':
        approval=read_json(root/CONTROL/'approvals'/(receipts[0]['declaration_sha256']+'.json'))
        require(verify_envelope(approval,signer.public) and approval['declaration_sha256']==receipts[0]['declaration_sha256'],'Declaration approval differs')
        require(all(read_json(run/'authorization.json')['approval_sha256']==approval['content_sha256'] for run in runs),'Run approval binding differs')
        outcomes=business_projection(runs[0])
        require(all(business_projection(run)==outcomes for run in runs[1:]),'Acceptance business outcomes differ across replays')
    output.mkdir(parents=True)
    manifest=signer.sign({'artifact_type':'lightyear-native-journey-publication','schema_version':'1.0',
        'mode':mode,'runs':receipts,'files':files,'business_outcomes':outcomes,'declaration_approval':approval,'authority_sha256':hashlib.sha256(signer.public).hexdigest(),
        'independently_attested':False})
    with zipfile.ZipFile(output/'evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr('manifest.json',canonical(manifest));archive.writestr('authority.public.pem',signer.public)
        for digest,source in sorted(blobs.items()):archive.writestr('blobs/'+digest,source if isinstance(source,bytes) else encode_blob(source.read_bytes())[0])
    summary=signer.sign({'artifact_type':'lightyear-native-journey-publication-receipt','runs':receipts,
        'mode':mode,'manifest_sha256':manifest['content_sha256'],'archive_sha256':file_hash(output/'evidence.zip'),
        'authority_sha256':hashlib.sha256(signer.public).hexdigest(),'file_count':len(files),'unique_blob_count':len(blobs),
        'archive_bytes':(output/'evidence.zip').stat().st_size,'independently_attested':False})
    save(output/'receipt.json',summary);(output/'authority.public.pem').write_bytes(signer.public)
    return summary


def verify_publication(folder,temporary_parent=None):
    """Trust the reviewed receipt/key pair, then recompute each deterministic gate."""
    receipt=read_json(folder/'receipt.json');key=(folder/'authority.public.pem').read_bytes()
    require(verify_envelope(receipt,key) and hashlib.sha256(key).hexdigest()==receipt['authority_sha256'],'Publication signature invalid')
    require(file_hash(folder/'evidence.zip')==receipt['archive_sha256'],'Publication archive changed')
    with zipfile.ZipFile(folder/'evidence.zip') as archive, tempfile.TemporaryDirectory(dir=temporary_parent) as temp:
        root=Path(temp);manifest=json.loads(archive.read('manifest.json'))
        require(verify_envelope(manifest,key) and manifest['content_sha256']==receipt['manifest_sha256'],'Publication manifest changed')
        require(archive.read('authority.public.pem')==key and manifest['authority_sha256']==receipt['authority_sha256'],'Archive authority differs')
        require(manifest['runs']==receipt['runs'] and manifest['mode']==receipt['mode'],'Publication scope differs')
        approval=manifest['declaration_approval']
        if receipt['mode']=='replay':
            require(verify_envelope(approval,key) and all(r['declaration_sha256']==approval['declaration_sha256'] for r in receipt['runs']),'Published approval differs')
        names=archive.namelist();expected={'manifest.json','authority.public.pem'}|{'blobs/'+f['blob_sha256'] for f in manifest['files'].values()}
        expected.update('blobs/'+c['blob_sha256'] for f in manifest['files'].values() for c in f.get('components',[]))
        require(len(names)==len(set(names)) and set(names)==expected,'Unexpected or duplicate archive members')
        trust=root/'work/ms87/operator/authority.public.pem';trust.parent.mkdir(parents=True);trust.write_bytes(key)
        allowed={r['run_id'] for r in receipt['runs']}
        for relative,entry in manifest['files'].items():
            p=safe_relative(relative);parts=p.parts
            native=parts[:len(RUNS.parts)]==RUNS.parts and len(parts)>len(RUNS.parts)+1 and parts[len(RUNS.parts)] in allowed
            builder=receipt['mode']=='extend' and parts[:2]==('work','ms88') and len(parts)>=4 and parts[2].startswith('build-') and '/'.join(parts[3:]) in BUILDER_FILES
            require(native or builder,'Evidence outside declared run/builder scope')
            data=decode_blob(archive.read('blobs/'+entry['blob_sha256']),entry,lambda digest:archive.read('blobs/'+digest))
            target=root/Path(*parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        from lightyear_calibration.journey_verify import verify_gate
        results=[]
        for record in receipt['runs']:
            run=root/RUNS/record['run_id'];terminal=verify_run_identity(run,key)
            require(terminal['content_sha256']==record['receipt_sha256'],'Published terminal differs')
            if receipt['mode']=='replay':
                require(read_json(run/'authorization.json')['approval_sha256']==approval['content_sha256'],'Published run approval binding differs')
            implementation_root=Path(__file__).resolve().parents[1]
            for relative,expected_hash in read_json(run/'plan.json')['implementation_sha256'].items():
                safe_relative(relative)
                require(matches_implementation(implementation_root/relative,expected_hash),'Use the implementation pinned by the publication plan')
            if receipt['mode']=='replay':
                gates={command:verify_gate(run,command)['passed'] for command in COMMANDS}
                require(business_projection(run)==manifest['business_outcomes'],'Recomputed business outcomes differ')
            else:
                plan=read_json(run/'plan.json');directory=safe_relative(plan['builder_directory'])
                require(directory.parts[:2]==('work','ms88') and len(directory.parts)==3,'Invalid published builder directory')
                build=root/Path(*directory.parts);generated=read_json(build/'receipt.json')
                require(verify_envelope(generated,key) and generated['content_sha256']==plan['builder_receipt_sha256']==terminal['builder_receipt_sha256'],'Published builder receipt differs')
                for name,field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256'),('workspace/LightyearPartialInvoiceTest.java','harness_sha256')]:
                    require(file_hash(build/name)==generated[field],'Published builder provenance differs')
                from lightyear_calibration.partial_invoicing import verify_run
                gates={'verify-partial-invoicing':verify_run(run)['passed'],'verify-cleanup':verify_gate(run,'verify-cleanup')['passed']}
            require(all(gates.values()),'Published native gate failed')
            results.append({'run_id':run.name,'gates':gates})
        return {'status':'verified-native-observations-offline','runs':results,'independently_attested':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['publish','verify'])
    parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--run',type=Path,action='append')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--temporary-parent',type=Path)
    args=parser.parse_args()
    result=publish(args.root.resolve(),[p.resolve() for p in args.run],args.output.resolve()) if args.command=='publish' else verify_publication(args.output.resolve(),args.temporary_parent)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
