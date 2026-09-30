"""Add A2 qualification sources without replacing any A1 implementation."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import require,seal
from lightyear_calibration.journey_order import file_hash,save
from tools.ms94_execution_snapshot import guard
from tools.ms94_diagnostic_controls_v6 import AREA


def prepare(source,base,destination):
    source,base,destination=[Path(p).resolve() for p in (source,base,destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Use a fresh diagnostic qualification snapshot')
    inherited=guard(base);origins={name:base/name for name in inherited['files']}
    extras=[source/'tools'/name for name in ('ms94_diagnostic_controls_v6.py','ms94_diagnostic_native_v6.py',
        'ms94_diagnostic_qualification_v6.py','ms94_diagnostic_publication_v6.py','ms94_diagnostic_snapshot_v6.py')]
    extras += list((source/AREA).rglob('*.java'))+list((source/AREA).rglob('*.json'))
    extras += list((source/'docs/calibration/idempiere-ms94/equipment-06/stage-a1').rglob('*.json'))
    for path in extras:
        name=path.relative_to(source).as_posix()
        require(path.is_file() and not path.is_symlink(),'Unsafe or missing snapshot input')
        require(name not in origins or file_hash(origins[name])==file_hash(path),'Cannot change an inherited input')
        origins[name]=path
    pins={}
    for name,path in sorted(origins.items()):
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        digest=file_hash(path);shutil.copyfile(path,target)
        require(file_hash(target)==file_hash(path)==digest,'Snapshot input changed during copy');pins[name]=digest
    value=seal({'artifact_type':'ms94-execution-source-snapshot','execution_root':str(destination),'files':pins,
        'independent_file_copies':True,'mutable_source_mount_forbidden':True,
        'base_snapshot_sha256':inherited['content_sha256'],'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json',value);guard(destination);return value
