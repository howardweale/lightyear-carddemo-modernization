"""Prospective scoped extraction after inventory and separate Tower approval.

No traversal of a Maven cache. All inputs must be selected by the saved resolved
runtime and inventory hashes. lib/modules is authoritative; jmods corroborate.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile
from .inventory import digest
from .archive import bundle_paths,folder_bytes,inspect as inspect_archive
from .resolved_runtime import read as read_resolution

def check(v,reason):
    if not v:raise ValueError(reason)

def assemble(inventory,resolution,*,launch_key=None,expected_launch=None,transient_copies=None,application_copies=None):
    check(inventory['schema']=='b06-image-inventory/1' and inventory['failure'] is None,'inventory-required')
    check(resolution['schema'] in ('b06-resolved-runtime/2','b06-resolved-runtime/3','b06-resolved-runtime/4','b06-resolved-runtime/5','b06-resolved-runtime/6') and resolution['resolved'] is True,'resolved-runtime-required')
    raw=resolution['configuration_utf8']
    modern=resolution['schema'] in ('b06-resolved-runtime/3','b06-resolved-runtime/4','b06-resolved-runtime/5','b06-resolved-runtime/6')
    encoding='iso-8859-1' if modern else 'utf-8'
    config=raw['config.ini'].encode(encoding);surefire=raw['surefire.properties'].encode(encoding)
    if modern:
        from .tycho_runtime import read as read_tycho
        parsed=read_tycho(config,surefire,json.loads(resolution['observation_utf8']),json.loads(resolution['fork_command_utf8']))
    else: parsed=read_resolution(config,surefire)
    check(resolution['installation_inputs']==parsed,'resolved-configuration-differs')
    from .runtime_producer import produce
    check(launch_key is not None and expected_launch is not None,'trusted-launch-authority-required')
    extra={'fork_command':resolution['fork_command_utf8'].encode('utf-8')} if modern else {}
    if resolution['schema'] in ('b06-resolved-runtime/4','b06-resolved-runtime/5','b06-resolved-runtime/6'): extra['transient_copies']=transient_copies
    elif transient_copies is not None: raise ValueError('legacy-transient-copies-refused')
    if resolution['schema'] in ('b06-resolved-runtime/5','b06-resolved-runtime/6'):extra['application_copies']=application_copies
    elif application_copies is not None:raise ValueError('legacy-application-copies-refused')
    rebuilt=produce(resolution['observation_utf8'].encode(),config,surefire,inventory,resolution['launch_receipt'],launch_key,expected_launch,**extra)
    check(rebuilt==resolution,'runtime-producer-replay-differs')
    records={r['path']:r for r in inventory['artifacts']}
    check(resolution.get('launch_observed') is True and resolution.get('framework_jar'),'observed-launch-resolution-required')
    paths=list(dict.fromkeys(resolution['equinox_bundles']+resolution['boot_classpath' if modern else 'surefire_booter_classpath']+[resolution['framework_jar'],resolution['jdk_modules']]))
    check(paths,'runtime-closure-empty')
    check(all(p in records for p in paths),'runtime-artifact-not-in-inventory')
    check(all(resolution['artifact_sha256'].get(p)==records[p]['sha256'] for p in paths),'resolution-inventory-bytes')
    artifacts=[records[p] for p in paths]
    # Directory counts alone cannot bound nested jar class contents: stop until
    # the resolution inventory supplies their measured expanded entry counts.
    check(all(not r['nested_archives'] or r.get('expanded_class_entries') is not None for r in artifacts),'nested-inventory-count-required')
    check(type(resolution.get('jdk_class_entries')) is int and resolution['jdk_class_entries']>0,'jimage-list-count-required')
    tool=resolution['jimage_tool']
    check(tool['path'] in records and tool['sha256']==records[tool['path']]['sha256'],'bound-jimage-tool-required')
    check(type(resolution.get('jdk_expanded_bytes')) is int and resolution['jdk_expanded_bytes']>0,
          'measured-jimage-expanded-byte-limit-required')
    return dict(schema='b06-runtime-closure/1',artifacts=artifacts,
        resolution_sha256=hashlib.sha256(json.dumps(resolution,sort_keys=True).encode()).hexdigest(),
        maximum_archive_bytes=sum(r['bytes'] for r in artifacts),
        maximum_expanded_bytes=sum(r.get('expanded_class_bytes',r['bytes']) for r in artifacts if r['path']!=resolution['jdk_modules'])+resolution['jdk_expanded_bytes'],jimage_tool=tool,
        maximum_classes=sum(r.get('expanded_class_entries',r['class_entries']) for r in artifacts if r['path']!=resolution['jdk_modules'])+resolution['jdk_class_entries'],
        jdk_modules=resolution['jdk_modules'],jdk_method='jimage extract from bound lib/modules',
        jmods_authoritative=False,native_admission=False)

def extract(closure,output,jimage,*,run=subprocess.run,application_copies=None):
    check(closure['schema']=='b06-runtime-closure/1','closure-schema')
    check(str(jimage)==closure['jimage_tool']['path'] and digest(Path(jimage))==closure['jimage_tool']['sha256'],
          'jimage-tool-changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    blobs=output/'classes';blobs.mkdir();rows=[];expanded=0
    def retain(raw,origin,member):
        nonlocal expanded
        check(len(rows)<closure['maximum_classes'],'measured-class-bound')
        expanded+=len(raw)
        check(expanded<=closure['maximum_expanded_bytes'],'measured-expanded-byte-bound')
        h=hashlib.sha256(raw).hexdigest();dest=blobs/h
        if not dest.exists():dest.write_bytes(raw)
        rows.append(dict(origin=origin,member=member,sha256=h,bytes=len(raw)))
    def archive(raw,origin,depth=0):
        check(depth<=4,'nested-archive-depth')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            inspect_archive(raw,budget=max(len(raw),closure['maximum_archive_bytes'],closure['maximum_expanded_bytes']))
            paths=bundle_paths(z)
            for member in paths:
                if member!='.' and member not in z.namelist() and not any(n.startswith(member.rstrip('/')+'/') for n in z.namelist()):raise ValueError('missing-bundle-class-path-entry')
            for e in z.infolist():
                check(e.file_size<=closure['maximum_expanded_bytes'] and not e.flag_bits&1,'archive-entry-bound')
                if e.filename.endswith('.class') and ('.' in paths or any(not p.endswith('.jar') and e.filename.startswith(p.rstrip('/')+'/') for p in paths)):retain(z.read(e),origin,e.filename)
                elif e.filename in paths and e.filename.endswith('.jar'):
                    archive(z.read(e),origin+'!/'+e.filename,depth+1)
    progress=output/'progress.jsonl'
    archive_bytes=0
    try:
        for row in closure['artifacts']:
            p=Path(row['path'])
            if row.get('kind')=='captured-application-bundle':
                check(isinstance(application_copies,dict) and row['capture_path'] in application_copies,'application-extraction-copy-required')
                raw=application_copies[row['capture_path']]
                check(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes'],'application-extraction-copy-changed')
            elif row.get('kind')=='folder-bundle':
                raw,observed=folder_bytes(p)
                check(all(observed[k]==row[k] for k in ('sha256','bytes','files')),'scoped-folder-changed')
            else:
                raw=p.read_bytes()
                check(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes'],'scoped-artifact-changed')
            archive_bytes+=row['bytes'];check(archive_bytes<=closure['maximum_archive_bytes'],'measured-archive-byte-bound')
            if str(p)==closure['jdk_modules']:
                dest=output/'jimage';dest.mkdir()
                bound_modules=output/'bound-modules';bound_modules.write_bytes(raw)
                done=run([str(jimage),'extract','--dir',str(dest),str(bound_modules)],capture_output=True,timeout=600,check=False)
                (output/'jimage.stdout').write_bytes(done.stdout);(output/'jimage.stderr').write_bytes(done.stderr)
                check(done.returncode==0,'jimage-extract-failed')
                for f in sorted(dest.rglob('*.class')):retain(f.read_bytes(),row['sha256'],f.relative_to(dest).as_posix())
            else:archive(raw,row['sha256'])
            with progress.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(path=row['path'],classes=len(rows)))+'\n')
    finally:
        (output/'classes.json').write_text(json.dumps(rows,sort_keys=True),encoding='utf-8')
    return dict(classes=rows,jdk_source='lib/modules',native_admission=False)
