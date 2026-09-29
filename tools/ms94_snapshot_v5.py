"""Independent copies of the accepted base and the declared invoice-type delta."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from tools.ms94_execution_snapshot import guard
from tools.ms94_stage_b_evidence import stage_a

EVIDENCE = Path('docs/calibration/idempiere-ms94/equipment-04')
EXTENSION = Path('docs/calibration/idempiere-ms94/invoice-type-qualification-01')


def prepare(source, base, destination, include_qualification=False):
    source, base, destination = [Path(p).resolve() for p in (source, base, destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Use a new execution snapshot')
    manifest = guard(base); stage_a(base, base/EVIDENCE)
    origins = {name:base/name for name in manifest['files']}
    extras = list((source/'tools').glob('ms94_*v5.py')) + [source/'tools/ms94_v5_gate.py']
    extras += list((source/'factory/idempiere/qualification-ms94-v5').rglob('*'))
    extras += [source/'docs/calibration/idempiere-ms94/stage-b-02'/n for n in
               ('human-review.json','classification.json','NEXT-CONTRACT.md')]
    if include_qualification:
        extras += list((source/EXTENSION).rglob('*.json'))
    for path in extras:
        if not path.is_file(): continue
        name = path.relative_to(source).as_posix()
        require(name not in origins or file_hash(origins[name]) == file_hash(path), 'Cannot override base snapshot input: '+name)
        origins[name] = path
    pins = {}
    for name, original in sorted(origins.items()):
        require(original.is_file() and not original.is_symlink(), 'Unsafe snapshot source')
        target = destination/name; target.parent.mkdir(parents=True, exist_ok=True)
        digest = file_hash(original); shutil.copyfile(original, target)
        require(file_hash(target) == digest == file_hash(original), 'Snapshot input changed during copy')
        pins[name] = digest
    value = seal({'artifact_type':'ms94-execution-source-snapshot','execution_root':str(destination),
                  'files':pins,'independent_file_copies':True,'mutable_source_mount_forbidden':True,
                  'base_snapshot_sha256':manifest['content_sha256'],'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json', value); guard(destination)
    stage_a(destination, destination/EVIDENCE)
    return value
