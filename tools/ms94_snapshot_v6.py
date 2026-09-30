"""Additive B04 qualification snapshot; inherited equipment stays byte-identical."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import require,seal
from lightyear_calibration.journey_order import file_hash,save
from tools.ms94_execution_snapshot import guard


def prepare(source,base,destination):
    source,base,destination=[Path(p).resolve() for p in (source,base,destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Use a fresh B04 qualification snapshot')
    inherited=guard(base);origins={name:base/name for name in inherited['files']}
    extras=[source/'tools'/name for name in ('qualification_feedback_v4.py','ms94_v6_gate.py',
        'ms94_native_v6.py','ms94_publication_v6.py','ms94_recheck_v6.py','ms94_snapshot_v6.py')]
    extras += [source/'docs/calibration/idempiere-ms94/stage-b-03'/name for name in
               ('classification.json','operator-adjudication.json')]
    for path in extras:
        name=path.relative_to(source).as_posix()
        require(path.is_file() and not path.is_symlink(),'Missing or unsafe snapshot source')
        require(name not in origins or file_hash(origins[name])==file_hash(path),'Cannot override inherited frozen file: '+name)
        origins[name]=path
    pins={}
    for name,path in sorted(origins.items()):
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        digest=file_hash(path);shutil.copyfile(path,target)
        require(file_hash(path)==file_hash(target)==digest,'Source changed during snapshot copy')
        pins[name]=digest
    value=seal({'artifact_type':'ms94-execution-source-snapshot','execution_root':str(destination),
        'files':pins,'independent_file_copies':True,'mutable_source_mount_forbidden':True,
        'base_snapshot_sha256':inherited['content_sha256'],'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json',value);guard(destination);return value
