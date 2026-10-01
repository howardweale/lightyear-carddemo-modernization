"""Add new dated sources while preserving every inherited A3 revision file."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard

from tools.ms94_dated_controls import AREA,CONTROLS

ADDED = ('tools/ms94_dated_controls.py','tools/ms94_dated_native.py',
         'tools/ms94_dated_qualification.py','tools/ms94_dated_snapshot.py',
         'tests/test_ms94_dated_qualification.py',
         *tuple((AREA/name/file).as_posix() for name in CONTROLS
                for file in ('LightyearOperationsTest.java','manifest.json')))



def prepare(source, base, destination):
    source, base, destination = [Path(p).resolve() for p in (source, base, destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots')
            and not destination.exists(), 'Use one new dated-source snapshot')
    inherited = guard(base)
    require(inherited['content_sha256'] == '45320454e8693c920b7a4d94d38c52e9d1136aad6ebb145f40f44668525d3a9e',
            'Unexpected inherited A3 revision snapshot')
    origins = {n: base/n for n in inherited['files']}
    prior = source/'docs/calibration/idempiere-ms94/equipment-06/stage-a3-r1'
    report, checked = [read_json(prior/n) for n in ('report.json', 'terminal-verification.json')]
    key = (base/'work/ms87/operator/authority.public.pem').read_bytes()
    require(all(verify_envelope(v, key) for v in (report, checked))
            and report['content_sha256'] == '8104c17aa6cdc0b5a977a4998ee0953004d5d2bb569114c351b502c3509f5cea'
            and not report['passed'] and checked['all_available_archives_replayed'] and checked['cleanup_verified']
            and checked['report_sha256'] == report['content_sha256'], 'Prior failure is not preserved')
    extras = list(ADDED) + [(prior/n).relative_to(source).as_posix()
                            for n in ('report.json', 'terminal-verification.json','clock-diagnosis.json')]
    for n in extras:
        require(n not in origins, 'Never overwrite inherited files')
        origins[n] = source/n
    pins = {}
    for n, p in sorted(origins.items()):
        require(p.is_file() and not p.is_symlink(), 'Missing or unsafe snapshot input')
        target = destination/n; target.parent.mkdir(parents=True, exist_ok=True)
        h = file_hash(p); shutil.copyfile(p, target)
        require(file_hash(target) == file_hash(p) == h, 'Snapshot copy changed'); pins[n] = h
    manifest = seal({'artifact_type': 'ms94-execution-source-snapshot',
        'execution_root': str(destination), 'files': pins, 'independent_file_copies': True,
        'mutable_source_mount_forbidden': True, 'base_snapshot_sha256': inherited['content_sha256'],
        'source_root_for_provenance_only': str(source)})
    save(destination/'execution-snapshot.json', manifest); guard(destination)
    return manifest
