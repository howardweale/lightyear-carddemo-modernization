"""Freeze additive A3 equipment and private admitted checkpoint inputs."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json,require,seal
from lightyear_calibration.journey_order import file_hash,save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard

ADDED=('src/lightyear_calibration/ms94_a3_restore.py','tools/ms94_a3_controls.py',
       'tools/ms94_a3_entry.py','tools/ms94_a3_native.py','tools/ms94_a3_private_runner.py',
       'tools/ms94_a3_publication.py','tools/ms94_a3_qualification.py','tools/ms94_a3_snapshot.py')


def prepare(source,base,destination):
    source,base,destination=[Path(x).resolve() for x in (source,base,destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Use one new A3 execution snapshot')
    inherited=guard(base);origins={n:base/n for n in inherited['files']}
    prior=source/'docs/calibration/idempiere-ms94/equipment-06/stage-a3-checkpoint-r1'
    report=read_json(prior/'report.json');checked=read_json(prior/'terminal-verification.json')
    key=(base/'work/ms87/operator/authority.public.pem').read_bytes()
    require(all(verify_envelope(v,key) for v in (report,checked)) and report['passed'] and checked['passed']
            and checked['report_sha256']==report['content_sha256'] and checked['cleanup_verified'],
            'Private checkpoint is not independently admitted')
    extras=list(ADDED)+[(prior/n).relative_to(source).as_posix() for n in ('plan.json','report.json','terminal-verification.json')]
    for n in extras:
        require(n not in origins or file_hash(origins[n])==file_hash(source/n),'Inherited source changed')
        origins[n]=source/n
    native=base/report['run_directory']
    require(read_json(native/'receipt.json')==report,'Checkpoint preparation native receipt differs')
    for n in ('checkpoint.json','oracle-entry-multisets.json','postgresql-entry-multisets.json'):
        origins['work/ms94/a3-private-checkpoint/'+n]=native/'derived-checkpoint'/n
    pins={}
    for n,p in sorted(origins.items()):
        require(p.is_file() and not p.is_symlink(),'Missing or unsafe snapshot input')
        target=destination/n;target.parent.mkdir(parents=True,exist_ok=True);h=file_hash(p)
        shutil.copyfile(p,target);require(file_hash(target)==file_hash(p)==h,'Snapshot copy changed');pins[n]=h
    manifest=seal({'artifact_type':'ms94-execution-source-snapshot','execution_root':str(destination),'files':pins,
        'independent_file_copies':True,'mutable_source_mount_forbidden':True,
        'base_snapshot_sha256':inherited['content_sha256'],'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json',manifest);guard(destination);return manifest
