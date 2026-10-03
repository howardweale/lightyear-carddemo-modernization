"""Add B05 integration without replacing any of the 980 qualified input files."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import require,read_json,seal
from lightyear_calibration.journey_order import save,file_hash
from tools.ms94_execution_snapshot import guard
from tools.ms94_b05_admission import APPROVED,CONFIG

def prepare(dev,base,destination):
    dev,base,destination=[Path(p).resolve() for p in (dev,base,destination)]
    require(destination.is_relative_to(dev/'work/ms94/execution-snapshots') and not destination.exists(),'Use a new immutable executable root')
    inherited=guard(base)
    binding=read_json(dev/APPROVED/'plan.json')['qualification_binding']
    require(inherited['content_sha256']==binding['snapshot_sha256'] and len(inherited['files'])==980,'Wrong qualification root')
    origins={n:base/n for n in inherited['files']}
    extras=list((dev/'tools').glob('ms94_b05_*.py'))+list((dev/'tests').glob('test_ms94_b05*.py'))
    extras+=list((dev/APPROVED).rglob('*'))+list((dev/CONFIG).rglob('*'))
    for p in extras:
        if not p.is_file():continue
        require(not p.is_symlink(),'Symlink forbidden')
        name=p.relative_to(dev).as_posix()
        require(name not in origins or file_hash(origins[name])==file_hash(p),'Qualified input replacement forbidden')
        origins[name]=p
    pins={}
    for name,p in sorted(origins.items()):
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        pins[name]=file_hash(p);shutil.copyfile(p,target)
        require(file_hash(target)==file_hash(p)==pins[name],'Input changed during freeze')
    manifest=seal({'artifact_type':'ms94-b05-execution-source-snapshot','files':pins,
        'execution_root':str(destination),'source_root_for_provenance_only':str(dev),
        'base_snapshot_sha256':inherited['content_sha256'],'inherited_files_unchanged':980,
        'independent_file_copies':True,'mutable_source_mount_forbidden':True,
        'approved_plan_sha256':read_json(dev/APPROVED/'plan.json')['content_sha256'],
        'approved_declaration_sha256':read_json(dev/APPROVED/'declaration.json')['content_sha256']})
    save(destination/'execution-snapshot.json',manifest);guard(destination);return manifest
