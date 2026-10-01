"""One additive B04 snapshot, preserving every paired A3 input unchanged."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from tools.ms94_execution_snapshot import guard
from tools.ms94_b04_admission import prerequisites

ADDED = tuple('tools/ms94_b04_'+n+'.py' for n in
              ('admission','controller','evidence','inputs','measure','native','publication','snapshot','transport'))
ADDED += ('tests/test_ms94_b04.py',
          'factory/idempiere/qualification-ms94-v8/b04-diagnostic-allowlists.json')


def prepare(source, base, destination):
    source, base, destination = [Path(p).resolve() for p in (source, base, destination)]
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots') and not destination.exists(),
            'Use one new B04 execution snapshot')
    inherited = guard(base)
    require(inherited['content_sha256'] == 'af6753c05f1a4407e44c09a7d3d8c338661ca8f119bf534c2a4aea8a8186899e',
            'Unexpected paired A3 snapshot')
    origins = {n:base/n for n in inherited['files']}
    extras = list(ADDED)
    extras += ['docs/calibration/idempiere-ms94/equipment-06/stage-a3-dated/'+n
               for n in ('plan.json','report.json','terminal-verification.json')]
    extras += ['docs/calibration/idempiere-ms94/stage-b-03/'+n
               for n in ('classification.json','operator-adjudication.json','trials/pilot-01/plan.json')]
    for name in extras:
        p = source/name
        require(name not in origins or file_hash(origins[name]) == file_hash(p), 'Cannot overwrite inherited input')
        origins[name] = p
    pins = {}
    for name, original in sorted(origins.items()):
        require(original.is_file() and not original.is_symlink(), 'Unsafe snapshot source')
        target = destination/name; target.parent.mkdir(parents=True, exist_ok=True)
        digest = file_hash(original); shutil.copyfile(original, target)
        require(file_hash(target) == file_hash(original) == digest, 'Snapshot source changed')
        pins[name] = digest
    manifest = seal({'artifact_type':'ms94-execution-source-snapshot','execution_root':str(destination),
        'files':pins,'independent_file_copies':True,'mutable_source_mount_forbidden':True,
        'base_snapshot_sha256':inherited['content_sha256'],'source_root_for_provenance_only':str(source)})
    save(destination/'execution-snapshot.json', manifest); guard(destination); prerequisites(destination)
    return manifest
