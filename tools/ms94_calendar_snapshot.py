"""Fresh calendar equipment snapshot; previous execution roots are immutable."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import require, seal
from lightyear_calibration.journey_order import file_hash, save
from tools.ms94_execution_snapshot import guard


def prepare(source, base, destination):
    source,base,destination=[Path(p).resolve() for p in (source,base,destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Calendar qualification requires a new execution snapshot')
    inherited=guard(base)
    require(inherited['content_sha256']=='af6753c05f1a4407e44c09a7d3d8c338661ca8f119bf534c2a4aea8a8186899e',
            'Unexpected prior qualified equipment snapshot')
    origins={name:base/name for name in inherited['files']}
    extras=list((source/'tools').glob('ms94_calendar*.py'))
    extras += [source/'tools/ms94_b04_feedback_route.py']
    extras += list((source/'factory/idempiere/qualification-ms94-v11/calendar').rglob('*'))
    extras += [source/'tests/test_ms94_calendar.py', source/'tests/test_qualification_feedback_v4.py']
    for p in extras:
        if not p.is_file():continue
        name=p.relative_to(source).as_posix()
        require(not p.is_symlink() and (name not in origins or file_hash(origins[name])==file_hash(p)),
                'Cannot replace inherited equipment file: '+name)
        origins[name]=p
    pins={}
    for name,p in sorted(origins.items()):
        require(p.is_file() and not p.is_symlink(),'Unsafe snapshot source')
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        digest=file_hash(p);shutil.copyfile(p,target)
        require(file_hash(target)==file_hash(p)==digest,'Source changed while freezing')
        pins[name]=digest
    value=seal({'artifact_type':'ms94-execution-source-snapshot','files':pins,'execution_root':str(destination),
                'base_snapshot_sha256':inherited['content_sha256'],'inherited_files_unchanged':len(inherited['files']),
                'independent_file_copies':True,'mutable_source_mount_forbidden':True,
                'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json',value);guard(destination);return value
