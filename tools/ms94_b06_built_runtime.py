"""Host assembly/mount and replay contract for B06's retained runtime."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, verify
from tools.ms94_b06_admission import bound_file, check
from tools.ms94_b06_classfile import inspect_class
from tools import ms94_b06_built_worker as worker


def required_inputs(spec):
    return {spec['compilation']['path']:spec['compilation']['sha256'],
            spec['manifest']['path']:spec['manifest']['sha256'],
            spec['properties']['path']:spec['properties']['sha256'],
            **{row['path']:row['sha256'] for row in spec['classes'].values()},
            **{row['path']:row['sha256'] for row in spec['configuration'].values()}}


def contract(root, plan):
    """Offline admission; paths are private and only hashes go into public plans."""
    spec = plan['built_runtime']; verify(spec)
    check(spec['schema']=='b06-built-native-inputs/1' and spec['image'].startswith('sha256:'), 'built-runtime-image-binding')
    check(spec['source_sha256']==plan['harness_sha256'], 'built-runtime-source-binding')
    for path, sha in required_inputs(spec).items(): bound_file(root,path,sha)
    manifest = read_json(Path(root)/spec['manifest']['path']); verify(manifest)
    check(manifest['content_sha256']==spec['manifest_sha256'], 'built-runtime-manifest-binding')
    compiled=read_json(Path(root)/spec['compilation']['path'])
    check(compiled['sha256']==spec['source_sha256'] and compiled['exit_code']==0 and
          compiled['model_calls']==compiled['native_pairs']==compiled['tests_run']==0, 'built-runtime-compilation-binding')
    check(len(compiled['classes'])==len(spec['classes']) and
          {r['sha256'] for r in compiled['classes']}=={r['sha256'] for r in spec['classes'].values()},
          'built-runtime-compiled-class-set')
    raw = (Path(root)/spec['properties']['path']).read_bytes()
    check(worker.descriptor(Path(root)/spec['properties']['path'])==manifest['sealed_files'][manifest['testproperties_path']], 'built-runtime-baseline-properties')
    properties = worker.properties(raw)
    overlays={}
    catalog=plan['posting_observer']['target_class_files_sha256']
    for entry, row in spec['classes'].items():
        check(worker.CLASS.fullmatch(entry), 'built-runtime-class-path')
        path=bound_file(root,row['path'],row['sha256']); identity=inspect_class(path.read_bytes())
        check(entry=='target/classes/'+identity['class'].replace('.','/')+'.class', 'built-runtime-class-name')
        check(catalog.get(row['path'])==row['sha256'], 'built-runtime-class-not-in-observer')
        overlays[entry]=worker.descriptor(path)
    prefix=worker.LAYER+'/configuration-seed/'
    expected={p[len(prefix):]:v for p,v in manifest['sealed_files'].items() if p.startswith(prefix)}
    check(set(expected)==set(spec['configuration']) and bool(expected), 'built-runtime-configuration-set')
    for name,row in spec['configuration'].items():
        check(not Path(name).is_absolute() and '..' not in Path(name).parts, 'built-runtime-config-path')
        check(worker.descriptor(Path(root)/row['path'])==expected[name], 'built-runtime-configuration-bytes')
    launch=worker.seal(dict(schema='b06-built-native-launch/1',image=spec['image'],
        manifest_sha256=manifest['content_sha256'],source_sha256=spec['source_sha256'],
        argv=worker.arguments(manifest),overlays=overlays,
        testproperties={'bytes':len(properties),'sha256':hashlib.sha256(properties).hexdigest()},
        model_calls=0,rebuild=False))
    worker.validate_spec(manifest, launch)
    check(plan['posting_observer'].get('expected_jvm_arguments')==launch['argv'], 'built-runtime-observer-command')
    return manifest,launch,properties


def prepare(root, run, plan, staging):
    manifest,launch,properties=contract(root,plan)
    root,staging=Path(root),Path(staging)
    spec=plan['built_runtime']
    inputs=Path(run)/'application-input'/staging.name;inputs.mkdir(parents=True,exist_ok=False)
    mutable=Path(run)/'application-state'/staging.name;mutable.mkdir(parents=True,exist_ok=False)
    config=mutable/'configuration';config.mkdir()
    for name,row in spec['configuration'].items():
        target=config/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(bound_file(root,row['path'],row['sha256']),target)
    for name in ('data','reports'):(mutable/name).mkdir()
    (inputs/'launch.json').write_bytes(worker.canonical(launch))
    (inputs/'surefire.properties').write_bytes(properties)
    from tools.b06_image_artifacts.standalone_content import reader_bytes
    (inputs/'bundle_content.py').write_bytes(reader_bytes())
    mounts=[(root/'tools/ms94_b06_built_worker.py','/runtime/worker.py',False),
            (inputs/'bundle_content.py','/runtime/bundle_content.py',False),
            (inputs/'launch.json','/runtime/launch.json',False),
            (inputs/'surefire.properties',manifest['testproperties_path'],False),
            (config,manifest['config_path'],True),(mutable/'data',manifest['data_path'],True),
            (mutable/'reports',worker.TEST+'/target/surefire-reports',True),
            (staging,'/results',True)]
    mounts.extend((root/row['path'],worker.TEST+'/'+entry,False) for entry,row in spec['classes'].items())
    check(len({dst for _,dst,_ in mounts})==len(mounts),'built-runtime-duplicate-mount')
    for source,_,writable in mounts:
        if not writable:
            check(not any(Path(source).resolve().is_relative_to(Path(other).resolve()) for other,_,rw in mounts if rw),
                  'built-runtime-writable-input-alias')
    args=['--read-only']
    for src,dst,writable in mounts:
        args+=['--mount',f'type=bind,src={src},dst={dst}'+('' if writable else ',readonly')]
    return args,[dict(destination=dst,writable=rw) for _,dst,rw in mounts],launch


def replay(root, plan, execution, folder):
    manifest,launch,_=contract(root,plan)
    check(execution.get('launch_sha256')==launch['content_sha256'] and execution.get('offline_maven') is False and
          execution.get('runtime_image')==launch['image'] and execution.get('application_readonly') is True, 'built-runtime-execution-binding')
    expected={}
    for name,row in manifest['base_applications'].items():
        entries=copy.deepcopy(row['entries'])
        if name=='org.idempiere.test':entries.update({k:dict(kind='file',**v) for k,v in launch['overlays'].items()})
        expected[name]=hashlib.sha256(worker.canonical(entries)).hexdigest()
    for name in ('built-before.json','built-after.json'):
        value=read_json(Path(folder)/name);worker.verify(value)
        check(value==worker.seal(dict(schema='b06-built-native-check/1',launch_sha256=launch['content_sha256'],
            manifest_sha256=manifest['content_sha256'],application_maps_sha256=expected,
            overlays=launch['overlays'],argv=launch['argv'],verified=True)), 'built-runtime-replay-differs')
        check(execution['built_runtime_checks_sha256'][name]==hashlib.sha256((Path(folder)/name).read_bytes()).hexdigest(), 'built-runtime-check-file-binding')
    return {'built_runtime_replayed':True,'launch_sha256':launch['content_sha256']}

def mount_contract(manifest, classes):
    return sorted([('/runtime/worker.py',False),('/runtime/bundle_content.py',False),('/runtime/launch.json',False),
        (manifest['testproperties_path'],False),(manifest['config_path'],True),(manifest['data_path'],True),
        (worker.TEST+'/target/surefire-reports',True),('/results',True),
        *((worker.TEST+'/'+entry,False) for entry in classes)])
