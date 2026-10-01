"""Freeze a fresh paired A3 while preserving all qualified dated-source files."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard

ADDED = ('tools/ms94_a3_dated_qualification.py','tools/ms94_a3_dated_snapshot.py',
         'tests/test_ms94_a3_dated_qualification.py')


def prepare(source, base, destination):
    source, base, destination = [Path(p).resolve() for p in (source, base, destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots')
            and not destination.exists(), 'Use one new paired dated-source snapshot')
    inherited = guard(base)
    require(inherited['content_sha256'] == '9275022150f63d0dfecaefb63f2464716a678dfe3e85e60cf4d77873e4cd0f48',
            'Unexpected inherited dated-source snapshot')
    origins = {n: base/n for n in inherited['files']}
    prior = source/'docs/calibration/idempiere-ms94/equipment-06/stage-dated-controls'
    report, checked = [read_json(prior/n) for n in ('report.json', 'terminal-verification.json')]
    key = (base/'work/ms87/operator/authority.public.pem').read_bytes()
    require(all(verify_envelope(v, key) for v in (report, checked))
            and report['content_sha256'] == 'fc66d4b95b1f85557b4c33f77141fd5612540f38e6590cb3e98380af8a72a2bf'
            and report['passed'] and checked['passed']
            and checked['content_sha256']=='f25c05966a99956b07d4480a4b6bdb789d675e67723e73f56753ff1953dbcbbb' and checked['all_available_archives_replayed'] and checked['cleanup_verified']
            and checked['report_sha256'] == report['content_sha256'], 'Dated-source prerequisite incomplete')
    extras = list(ADDED) + [(prior/n).relative_to(source).as_posix()
                            for n in ('plan.json','report.json','terminal-verification.json')]
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
