"""New Stage B root: exact qualified bytes plus declared controller additions."""
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json, require, seal
from lightyear_calibration.journey_order import file_hash, save
from tools.ms94_execution_snapshot import guard
from tools.ms94_stage_b_evidence import stage_a
from tools.ms94_public_api_v4 import CATALOG

EVIDENCE = Path('docs/calibration/idempiere-ms94/equipment-04')
MODULES = ('ms94_controller_v4', 'ms94_broker_v4', 'ms94_builder_mcp_v4',
           'ms94_tool_policy_v4', 'ms94_transport_v4', 'ms94_native_b_v4',
           'ms94_measure_v4', 'ms94_publication_b_v4', 'ms94_stage_b_evidence',
           'ms94_public_api_v4', 'ms94_stage_b_snapshot')


def prepare(source, qualified, destination):
    source, qualified, destination = map(lambda p: Path(p).resolve(), (source, qualified, destination))
    require(destination.is_relative_to(source/'work/ms94/execution-snapshots')
            and not destination.exists(), 'Use a new dedicated Stage B snapshot')
    guard(qualified)
    equipment, _ = stage_a(qualified, source/EVIDENCE)
    origins = {name: qualified/name for name in equipment['implementation_sha256']}
    extras = ['tools/'+name+'.py' for name in MODULES]
    extras += [CATALOG, 'factory/idempiere/repeatability/baseline/builder-input.json',
               'factory/idempiere/analyst-repair/api-provenance.json']
    extras += [p.relative_to(source).as_posix() for p in (source/EVIDENCE).rglob('*.json')]
    for name in extras:
        require(name not in origins or file_hash(source/name) == file_hash(origins[name]),
                'Stage B may not override qualified code: '+name)
        origins[name] = source/name
    # Files are independent copies, including the one test whose working-tree
    # line endings differ from the qualified source. No old hash is normalized.
    pins = {}
    for name, original in sorted(origins.items()):
        require(original.is_file() and not original.is_symlink(), 'Unsafe snapshot source')
        target = destination/name; target.parent.mkdir(parents=True, exist_ok=True)
        digest = file_hash(original); shutil.copyfile(original, target)
        require(file_hash(target) == digest == file_hash(original), 'Source changed during copy')
        pins[name] = digest
    value = seal({'artifact_type':'ms94-execution-source-snapshot','files':pins,
        'execution_root':str(destination),'independent_file_copies':True,
        'source_root_for_provenance_only':str(source),'mutable_source_mount_forbidden':True,
        'qualified_equipment_plan_sha256':equipment['content_sha256']})
    save(destination/'execution-snapshot.json', value)
    guard(destination); stage_a(destination, destination/EVIDENCE)
    return value
