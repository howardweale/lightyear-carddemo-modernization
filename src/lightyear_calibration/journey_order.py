"""Declared native journey replay. Live observations never inherit fixture verdicts."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from .contracts import canonical, digest, read_json, require, seal, verify
from lightyear_factory.contracts import WorkOrder, GateContract
from lightyear_factory.agents import LocalAgentSet

ORDER = Path('factory/idempiere/ms86-journeys/work-order.json')
RUNS = ORDER.parent / 'runs'
LANES = ('oracle', 'postgresql')
CASES = ('boundary', 'diagnostic-first-only', 'operations')
GATES = ('entry-state', 'business-outcomes', 'difference-admission', 'declared-footprint', 'known-findings', 'cleanup')
COMMANDS = ('verify-entry', 'verify-outcomes', 'verify-differences', 'verify-footprint', 'verify-known-findings', 'verify-cleanup')
BOUNDARIES = Path('docs/calibration/idempiere-boundaries')
UNCLAIMED = dict(schema_equivalence=False, application_equivalence=False,
                 platform_qualification=False, independently_attested=False, bounded_boundary_equivalence=False)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def within(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'Unsafe relative path')
    p = root / relative
    require(not any(x.is_symlink() for x in (p, *p.parents)), 'Symbolic input path')
    require(p.resolve().is_relative_to(root.resolve()), 'Path escapes workspace')
    return p


def load_order(root):
    value = read_json(root / ORDER)
    require(value['schema_version'] == '1.0' and value['template_type'] == 'native-journey-campaign', 'Unknown journey schema')
    require(value['mode'] == 'replay', 'This engine accepts replay declarations only')
    p = value['policy']; e = value['environment']
    require(p['max_model_calls'] == 0 and type(p['max_model_calls']) is int, 'Replay has no model budget')
    require(p['allow_network'] is False and e['cloud_resources'] is False and e['network'] == 'internal-only', 'Local isolation required')
    require(e['max_parallel_pairs'] == 1 and e['pairs'] == ['boundary', 'operations'], 'Unsupported pair schedule')
    require(p['agent_set'] == 'local' and type(p['max_attempts']) is int and 1 <= p['max_attempts'] <= 2, 'Unsupported replay agent/retry budget')
    require(p['retry_only_for'] == ['container-start', 'timeout', 'transient-io'], 'Retry authority cannot increase')
    require(type(p['max_elapsed_seconds']) is int and 60 <= p['max_elapsed_seconds'] <= 14400, 'Invalid elapsed budget')
    require(value['scope']['allowed_paths'] == [RUNS.as_posix()+'/'], 'Unexpected writable scope')
    require(value['acceptance']['gate_output_exposed_to_builder'] is False, 'Verifier output is private')
    for definition, gate_id, command in zip(value['acceptance']['gates'], GATES, COMMANDS, strict=True):
        gate = GateContract.from_dict(definition)
        require(gate.gate_id == gate_id and list(gate.command) == ['python', '-m', 'lightyear_calibration.journey_order', command, '--run', '{run}'], 'Unsupported gate command')
        require(not gate.expose_output_to_builder, 'Verifier output is private')
    require({x['id'] for x in value['application']['harnesses']} == {'boundary', 'operations'}, 'Unexpected harness set')
    for h in value['application']['harnesses']:
        require(h['pair'] == h['id'] and h['test'] in ('LightyearBoundaryTest', 'LightyearOperationsTest'), 'Unsupported harness')
        require(file_hash(within(root, h['file'])) == h['sha256'], 'Declared harness hash mismatch')
    require(value['application']['jvm_properties'] == {'user.timezone': 'UTC'}, 'UTC JVM required')
    from .boundary_contract import INPUT
    require(value['expected']['boundary']=={
        'customer_name_preserved':INPUT['customer_name'],'empty_description_stored_as':None,
        'net_total':'53.99','tax':'4.05','invoice_and_payment':'58.04','stock':{'opening':10,'closing':7}},
        'Declared business expectations differ from the immutable verifier')
    require(value['expected']['operations']=={'partial_shipments':[1,2],'credit_memo':'19.35','reversal':'-19.35',
        'rollback_then_retry_creates_no_duplicate':True,'locked_updates':['100.00','100.01','100.02'],
        'new_application_issues':0,'unresolved_differences':0},'Declared operations differ from verifier')
    require(set(value['differences']['admitting_rules'])=={
        'application-clock-within-native-execution','fresh-unique-application-uuid','fresh-unique-generated-UUID',
        'exact-native-decimal-value','nonnegative-workflow-duration-bounded-by-execution',
        'workflow-text-identical-with-exact-decimal-rendering','processed-epoch-milliseconds-within-native-execution',
        'pinned-driver-address-matches-isolated-native-target','oracle-native-database-name-and-unchanged-postgresql-seed-metadata'},
        'Declared admitting rules differ from the MS86 native evidence')
    for lane in LANES:
        require(re.fullmatch('sha256:[a-f0-9]{64}', e['engines'][lane]['image_digest']), 'Images require exact identities')
    require(value['cleanup']['containers'] == value['cleanup']['network'] == 'remove'
            and value['cleanup']['credentials'] == 'destroy'
            and value['cleanup']['retain_data_on_failure'] is True
            and set(value['cleanup']['runs_on']) == {'success','failure','cancel','timeout','halt'}, 'Mandatory cleanup contract changed')
    require([x['id'] for x in value['known_findings']] == ['oracle-shipdate-fractional-seconds','oracle-first-only-for-update'], 'Unexpected known findings')
    return value


def factory_order(value):
    # The general builder contract requires a positive call budget. Its immutable
    # replay projection reduces that authority to zero and never calls build().
    projected = json.loads(json.dumps(value))
    projected['policy']['max_model_calls'] = 1
    projected['acceptance']['max_attempts'] = value['policy']['max_attempts']
    return replace(WorkOrder.from_dict(projected), max_model_calls=0, max_model_cost_usd=0)


def diagnostic_profile(row):
    return {**{k:row[k] for k in ('loggername','sourceclassname','sourcemethodname')},
            'root_error':row['stacktrace'].splitlines()[0]}


def archived(root):
    """Resolve every supporting byte through a verified publication manifest."""
    r = read_json(root / BOUNDARIES / 'receipt.json'); verify(r)
    archive = root / BOUNDARIES / 'evidence.zip'
    require(file_hash(archive) == r['evidence_archive']['sha256'], 'Published archive hash mismatch')
    with zipfile.ZipFile(archive) as z:
        def get(name):
            data = z.read('evidence/'+name)
            require(hashlib.sha256(data).hexdigest() == r['evidence_files']['evidence/'+name], 'Archived member hash mismatch')
            return data
        diagnostic_state=json.loads(get('diagnostic-first-only/states/after-oracle.json'))
        issue_file=diagnostic_state['tables']['ad_issue']['header']['raw_file']
        issue_rows=[json.loads(line) for line in gzip.decompress(get('diagnostic-first-only/rows/after/oracle/'+issue_file)).splitlines()]
        profiles=sorted([diagnostic_profile(row) for row in issue_rows],key=canonical)
        inputs = {'diagnostic-issues.json':canonical(profiles),'checkpoint.json': get('ms84-checkpoint.json'),
                  'primary-keys.json': get('fractional/final/primary-keys.json'),
                  'diagnostic.java': get('diagnostic-first-only/oracle/harness.java')}
        require(inputs['diagnostic.java'] == get('diagnostic-first-only/postgresql/harness.java'), 'Diagnostic lanes use different harnesses')
        for lane in LANES:
            inputs[lane+'-repairs.json'] = get(f'fractional/baseline/{lane}-repair-execution.json')
            inputs[lane+'-entry-manifest.json'] = get(f'fractional/states/before-{lane}.json')
            manifest = json.loads(inputs[lane+'-entry-manifest.json']); verify(manifest)
            # Compact expected row multisets support complete entry-state checks.
            multisets = {}
            for table, item in manifest['tables'].items():
                raw = get(f"states/blobs/{item['row_multiset_sha256']}.json")
                require(digest(json.loads(raw)) == item['row_multiset_sha256'], 'Expected multiset mismatch')
                multisets[table] = json.loads(raw)
            inputs[lane+'-entry-multisets.json'] = canonical(multisets)
        return inputs


def resolved(root):
    order = load_order(root)
    refs = {name: file_hash(within(root, order['starting_state'][name]['receipt']))
            for name in ('checkpoint','schema_successor')}
    for name in ('checkpoint','schema_successor'):
        verify(read_json(within(root, order['starting_state'][name]['receipt'])))
    inputs = archived(root)
    checkpoint = json.loads(inputs['checkpoint.json']); verify(checkpoint)
    schema = read_json(within(root, order['starting_state']['schema_successor']['receipt']))
    require(checkpoint['admitted'] and checkpoint['content_sha256'] == schema['baseline_checkpoint_sha256'], 'Checkpoint/schema lineage differs')
    return order, inputs, refs


def make_plan(root, local, inventory):
    order, inputs, refs = resolved(root)
    require(inventory['memory_bytes'] >= 12*1024**3 and inventory['free_bytes'] >= 60*1024**3, 'Insufficient local memory or free disk')
    require(inventory['images'] == {k:v['image_digest'] for k,v in order['environment']['engines'].items()}, 'Pinned database image is missing')
    require(re.fullmatch('sha256:[a-f0-9]{64}',local['runner_image']), 'Runner must be pinned')
    require(local['offline_build_verified'] is True, 'Runner dependencies require an offline build preflight')
    implementation = {p.relative_to(root).as_posix():file_hash(p) for package in ('lightyear_calibration','lightyear_workflow','lightyear_factory','lightyear_execution')
                      for p in sorted((root/'src'/package).glob('*.py')) if p.name not in {'journey_builder.py','partial_invoicing.py'}}
    plan = {'artifact_type':'lightyear-native-journey-plan', 'declaration_sha256':file_hash(root/ORDER),
            'declaration':order,'references':refs,'inputs_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in inputs.items()},
            'implementation_sha256':implementation,'local':local,
            'cases':list(CASES),'diagnostic_harness_sha256':hashlib.sha256(inputs['diagnostic.java']).hexdigest(),
            'diagnostic_resolution':'MS86 archived original firstOnly harness, unchanged; separate fresh pair',
            'resources':{'network':'one Docker internal network per pair, no published ports',
                         'containers':'Oracle, PostgreSQL and offline application/verification runner, sequential pairs',
                         'created_data':'fresh PostgreSQL volume and Oracle writable layer per pair',
                         'destroyed':'all run containers, private networks and ephemeral credentials',
                         'retained_on_failure':'database snapshots without plaintext credential configuration'},
            'preflight_minimum':{'memory_bytes':12*1024**3,'free_bytes':60*1024**3},
            'factory_plan':LocalAgentSet().plan(factory_order(order), {'limitations':['Replay has no builder or model calls.']}),
            'cloud_resources':False,'model_calls':0,**UNCLAIMED}
    return seal(plan)


def validate_plan(root, plan, local, inventory):
    verify(plan)
    require(make_plan(root,local,inventory) == plan, 'Stale plan digest; review the current plan before start')


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(value))


def known_findings(boundary, diagnostic):
    """Strict expected failures are distinct from a passing equivalence claim."""
    findings=boundary['failed_input_preservation_or_business_checks']
    expected={'lane':'oracle','check':'fractional-shipment-timestamp-preserved',
              'observed':'2026-09-26T12:34:56','expected':'2026-09-26T12:34:56.123456','passed':False}
    return {'timestamp':findings == [expected] and boundary['passed_check_count']=={'oracle':14,'postgresql':15},
            'locking':diagnostic.get('oracle_exit_code') == 1 and diagnostic.get('postgresql_exit_code') == 0
                      and diagnostic.get('exact_oracle_error') is True and diagnostic.get('postgresql_completed') is True}


def classify(code):
    return {'classification':code,'retryable':code in {'container-start','timeout','transient-io'},
            'action':{'unknown-difference':'propose-normalization','known-finding-changed':'classify-intentional-change',
                      'timestamp-contract':'accept-contract-equivalence'}.get(code)}


def gate(run, command):
    """Each gate recomputes its checks from captured native artifacts."""
    from .journey_verify import verify_gate
    require(command in COMMANDS,'Unknown journey gate')
    return verify_gate(run,command)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=[*COMMANDS,'plan','approve','start','status','cancel','recover','decision','resume'])
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--run',type=Path)
    parser.add_argument('--actor');parser.add_argument('--reason');parser.add_argument('--plan-sha256')
    parser.add_argument('--decision-id');parser.add_argument('--outcome')
    args=parser.parse_args();root=args.root.resolve()
    if args.command in COMMANDS:
        result=gate(args.run.resolve(),args.command)
    else:
        from .journey_runtime import dispatch_command
        result=dispatch_command(root,args)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result.get('passed',True) else 3


if __name__=='__main__':raise SystemExit(main())
