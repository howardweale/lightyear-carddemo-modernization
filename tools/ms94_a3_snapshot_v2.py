"""Add the corrected signing boundary without changing any original A3 source."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard

ADDED = ('tools/ms94_a3_entry_v2.py', 'tools/ms94_a3_native_v2.py',
         'tools/ms94_a3_qualification_v2.py', 'tools/ms94_a3_snapshot_v2.py',
         'tests/test_ms94_a3_entry_v2.py')


def prepare(source, base, destination):
    source, base, destination = [Path(p).resolve() for p in (source, base, destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots')
            and not destination.exists(), 'Use one new A3 revision snapshot')
    inherited = guard(base)
    require(inherited['content_sha256'] == '7de8c8c4f278e37426ac724d868511e2476369cd0dc4782758f1eb73b03df437',
            'Unexpected original A3 snapshot')
    origins = {n: base/n for n in inherited['files']}
    prior = source/'docs/calibration/idempiere-ms94/equipment-06/stage-a3'
    report, checked = [read_json(prior/n) for n in ('report.json', 'terminal-verification.json')]
    key = (base/'work/ms87/operator/authority.public.pem').read_bytes()
    require(all(verify_envelope(v, key) for v in (report, checked))
            and report['content_sha256'] == '70e684a358413ebba38854e5e6420f08485ffba3a9414737c978436afa35d343'
            and not report['passed'] and checked['failure_reproduced'] and checked['cleanup_verified']
            and checked['report_sha256'] == report['content_sha256'], 'Prior failure is not preserved')
    extras = list(ADDED) + [(prior/n).relative_to(source).as_posix()
                            for n in ('report.json', 'terminal-verification.json')]
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
