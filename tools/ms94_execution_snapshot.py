"""Copy declared execution inputs into a separate root before freezing a plan.

No symlinks/hardlinks, generation, Docker calls or shared mutable source mount.
The resulting root is the only root a future controller should receive.
"""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import require,read_json,seal,verify
from lightyear_calibration.journey_order import file_hash,save,ORDER,BOUNDARIES


def copy_snapshot(source,destination,relative_files):
    source=Path(source).resolve();destination=Path(destination).resolve()
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots'),
            'Execution snapshot must stay in its dedicated workspace directory')
    require(not destination.exists(),'Execution snapshots are never overwritten')
    selected={}
    for name in sorted(set(relative_files)):
        path=Path(name)
        require(not path.is_absolute() and '..' not in path.parts,'Unsafe snapshot path')
        original=source/path
        require(original.is_file() and not any(p.is_symlink() for p in (original,*original.parents)),
                'Snapshot source must be a regular non-symbolic file')
        require(original.resolve().is_relative_to(source) and not original.resolve().is_relative_to(destination),
                'Snapshot input escaped source')
        selected[path.as_posix()]=file_hash(original)
    destination.mkdir(parents=True)
    for name,digest in selected.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
        require(file_hash(target)==digest and file_hash(source/name)==digest,'Source changed during snapshot copy')
    manifest=seal({'artifact_type':'ms94-execution-source-snapshot','files':selected,
        'independent_file_copies':True,'execution_root':str(destination),
        'source_root_for_provenance_only':str(source),'mutable_source_mount_forbidden':True})
    save(destination/'execution-snapshot.json',manifest)
    return manifest


def native_files(root):
    root=Path(root);names=set()
    for folder,pattern in [('src','**/*.py'),('tools','*.py'),
        ('factory/idempiere/qualification','**/*'),('factory/idempiere/qualification-ms94','**/*'),
        ('factory/idempiere/qualification-ms94-v3','**/*'),(str(BOUNDARIES),'**/*')]:
        names.update(p.relative_to(root).as_posix() for p in (root/folder).glob(pattern)
                     if p.is_file() and '__pycache__' not in p.parts)
    order=read_json(root/ORDER);names.add(ORDER.as_posix())
    names.update(h['file'] for h in order['application']['harnesses'])
    names.update(order['starting_state'][n]['receipt'] for n in ('checkpoint','schema_successor'))
    names.update(('factory/idempiere/repeatability/comparison-register.json',
                  'work/ms87/local-runtime.json','work/ms87/operator/authority.public.pem'))
    packet=read_json(root/'factory/idempiere/qualification-ms94-v3/review-packet.json')
    names.update(packet['files'])
    # Operator private key is deliberately not a publishable source input.
    # Provision signing authority separately when authorizing an actual snapshot.
    return sorted(names)


def guard(root):
    root=Path(root).resolve();manifest=read_json(root/'execution-snapshot.json');verify(manifest)
    require(str(root)==manifest['execution_root'],'Snapshot execution root differs')
    require(all(file_hash(root/name)==digest for name,digest in manifest['files'].items()),
            'Execution snapshot source changed')
    for folder in ('src','tools'):
        expected={n for n in manifest['files'] if n.startswith(folder+'/') and n.endswith('.py')}
        actual={p.relative_to(root).as_posix() for p in (root/folder).rglob('*.py')}
        require(expected==actual,'Execution snapshot module inventory changed')
    return manifest
