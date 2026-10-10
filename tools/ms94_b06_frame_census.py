"""Read-only r10 evidence census; no replay acceptance, Docker, signing or launch.

Run from the frozen snapshot with PYTHONPATH=src;. so existing readers/imports
come from that snapshot. Outputs must be a fresh directory outside the snapshot.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

from lightyear_calibration.contracts import read_json, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_executable import verify_snapshot
from tools.ms94_b06_posting_replay import catalog, CANDIDATE, SUPPORT, FRAMEWORK


def scope(name):
    if name == CANDIDATE or name.startswith(CANDIDATE + '$'):
        return 'candidate'
    if name == SUPPORT or name.startswith(SUPPORT + '$'):
        return 'support'
    if name.startswith(('java.', 'jdk.', 'sun.', 'com.sun.')):
        return 'JDK'
    if name.startswith(('org.compiere.', 'org.adempiere.', 'org.idempiere.')):
        return 'iDempiere application'
    if name.startswith(('org.junit.', 'junit.', 'org.opentest4j.', 'org.eclipse.', 'org.osgi.', 'org.apache.maven.surefire.')):
        return 'OSGi/Tycho/JUnit framework'
    return 'other dependency'


def generated_kind(name):
    # Name morphology is for inventory only, never proof of generation or host.
    if '$$Lambda/' in name or '$$Lambda$' in name:
        return 'lambda/hidden-name'
    if name.startswith(('jdk.internal.reflect.Generated', 'sun.reflect.Generated')):
        return 'reflection-accessor-name'
    if name.startswith(('jdk.proxy', 'com.sun.proxy.')) or '.$Proxy' in name:
        return 'proxy-name'
    if '/0x' in name:
        return 'hidden-name'
    return None


def required_r10(name, classes):
    return (name in classes or name == SUPPORT or name.startswith(CANDIDATE)
            or name in FRAMEWORK or name.startswith(('org.junit.', 'org.opentest4j.', 'junit.framework.')))


def binding(frame, classes):
    item = classes.get(frame['class'])
    if item is None:
        return 'UNBOUND'
    key = frame['method'] + frame['signature']
    if (frame['constant_pool_sha256'] != item['constant_pool_sha256']
            or frame['method_sha256'] != item['methods'].get(key)):
        return 'BOUND-BUT-MISMATCH'
    return 'BOUND-MATCH'


def checked(record, key):
    if not verify_envelope(record, key):
        raise ValueError('signature invalid: ' + str(record.get('artifact_type')))
    return record


def census_lane(root, run, lane, plan, key, classes):
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(plan, run)
    folder = run / 'posting-observer' / lane
    receipt = checked(read_json(folder / 'receipt.json'), key)
    refuse_engineering(receipt, folder)
    execution = read_json(run / 'cases/operations/1/execution' / lane / 'execution.json')
    refuse_engineering(execution, run)
    verify(execution)
    assert receipt['plan_sha256'] == plan['content_sha256']
    assert receipt['execution_sha256'] == execution['content_sha256']
    assert receipt['lane'] == lane and receipt['complete'] is True
    assert receipt['target']['image'] == plan['local']['runner_image']
    assert receipt['observer_class_files_sha256'] == plan['posting_observer']['class_files_sha256']
    from tools.ms94_b06_bytecode_policy import validate_jvm
    validate_jvm(receipt['target']['jvm'], plan['posting_observer'])
    raw = (folder / 'events.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == receipt['event_file_sha256']
    records = [json.loads(line) for line in raw.splitlines()]
    assert len(records) == receipt['event_count']
    previous = None
    rows, catches, readbacks = {}, set(), 0
    kinds = collections.Counter()
    first_failure = None
    terminals = []
    for seq, item in enumerate(records, 1):
        verify(item)
        assert item['previous_sha256'] == previous
        previous = item['content_sha256']
        event = item['event']
        assert event['sequence'] == seq
        kinds[event['kind']] += 1
        if event['kind'] == 'test-terminal':
            terminals.append({k: event[k] for k in ('sequence', 'status', 'test_class', 'test_method')})
        if event.get('document'):
            rb = read_json(folder / ('readback-%06d.json' % seq))
            verify(rb)
            assert rb['content_sha256'] == item['readback_sha256']
            assert rb['lane'] == lane and rb['event_sequence'] == seq
            assert rb['document'] == event['document']
            readbacks += 1
        else:
            assert item['readback_sha256'] is None
        for field, frames in (('frames', event.get('frames', [])),
                              ('catch_location', [event['catch_location']] if event.get('catch_location') else [])):
            for position, frame in enumerate(frames):
                name, method = frame['class'], frame['method'] + frame['signature']
                identity = (name, method, frame['loader'], frame['constant_pool_sha256'], frame['method_sha256'])
                generated = generated_kind(name)
                row = rows.setdefault(identity, {
                    'lane': lane, 'class': name, 'method': frame['method'], 'signature': frame['signature'],
                    'category': 'generated/hidden' if generated else scope(name),
                    'name_scope_only': scope(name), 'generated_name_kind': generated,
                    'binding': binding(frame, classes), 'r10_check_required': required_r10(name, classes),
                    'loader': frame['loader'], 'constant_pool_sha256': frame['constant_pool_sha256'],
                    'method_sha256': frame['method_sha256'], 'first_sequence': seq,
                    'stack_occurrences': 0, 'catch_occurrences': 0,
                })
                row['stack_occurrences' if field == 'frames' else 'catch_occurrences'] += 1
                if field == 'catch_location':
                    catches.add((name, method))
                if (field == 'frames' and first_failure is None and row['r10_check_required']
                        and row['binding'] != 'BOUND-MATCH'):
                    first_failure = {'sequence': seq, 'frame_index': position, 'kind': event['kind'],
                                     'class': name, 'method': method, 'binding': row['binding']}
    assert previous == receipt['last_event_sha256']
    assert records[0]['event']['kind'] == 'ready' and records[-1]['event']['kind'] == 'vm-death'
    values = sorted(rows.values(), key=lambda r: (r['class'], r['method'], r['signature'], r['loader']))
    stack_rows = [r for r in values if r['stack_occurrences']]
    categories = {}
    for cat in sorted({r['category'] for r in stack_rows}):
        subset = [r for r in stack_rows if r['category'] == cat]
        categories[cat] = {
            'classes': len({r['class'] for r in subset}),
            'methods': len({(r['class'], r['method'], r['signature']) for r in subset}),
            'unbound_classes': len({r['class'] for r in subset if r['binding'] == 'UNBOUND'}),
            'mismatched_methods': len({(r['class'], r['method'], r['signature']) for r in subset if r['binding'] == 'BOUND-BUT-MISMATCH'}),
        }
    summary = {
        'receipt_sha256': receipt['content_sha256'], 'events_sha256': receipt['event_file_sha256'],
        'event_count': len(records), 'event_kinds': dict(kinds), 'readback_hashes_verified': readbacks,
        'signature_and_chain_verified': True, 'ready_and_vm_death_present': True,
        'classes': len({r['class'] for r in stack_rows}),
        'methods': len({(r['class'], r['method'], r['signature']) for r in stack_rows}),
        'categories': categories, 'first_r10_binding_failure': first_failure, 'terminals': terminals,
        'catch_locations_catalogued_separately': len(catches),
        'full_observer_replay_passed': False, 'runtime_provenance_census_complete': False,
    }
    return summary, values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--snapshot-sha256', required=True)
    parser.add_argument('--campaign', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    if out.is_relative_to(root) or out.exists():
        raise ValueError('output must be new and outside frozen root')
    manifest = verify_snapshot(root, args.snapshot_sha256)
    run = root / 'factory/idempiere/ms86-journeys/runs' / args.run_id
    assert run.resolve().parent == (root / 'factory/idempiere/ms86-journeys/runs').resolve()
    key = (root / 'work/ms87/operator/authority.public.pem').read_bytes()
    plan = read_json(run / 'plan.json'); verify(plan)
    catalogues = catalog(root, plan['posting_observer']['target_class_files_sha256'])
    signed = {}
    for name in ('report.json', 'stopping.json', args.run_id + '-recovery.json'):
        record = checked(read_json(args.campaign / name), key)
        signed[name] = record['content_sha256']
    result = {'schema': 'b06-r10-offline-frame-census/1', 'review': 'operator review; not independent attestation',
              'snapshot_sha256': args.snapshot_sha256, 'frozen_files_verified': len(manifest['files_sha256']),
              'native_plan_sha256': plan['content_sha256'], 'preserved_signed_records': signed,
              'catalogue_classes': len(catalogues), 'lanes': {}, 'model_calls': 0, 'docker_calls': 0,
              'native_runs': 0, 'signatures_created': 0, 'historical_verdict_changed': False}
    all_rows = []
    for lane in ('oracle', 'postgresql'):
        result['lanes'][lane], rows = census_lane(root, run, lane, plan, key, catalogues)
        all_rows.extend(rows)
    verify_snapshot(root, args.snapshot_sha256)
    out.mkdir(parents=True, exist_ok=False)
    with (out / 'observed-frames.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader(); writer.writerows(all_rows)
    (out / 'observed-frames.json').write_text(json.dumps(all_rows, indent=2) + '\n', encoding='utf-8')
    result['inventory_file_sha256'] = {n: hashlib.sha256((out / n).read_bytes()).hexdigest()
                                       for n in ('observed-frames.csv', 'observed-frames.json')}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    md = ['# r10 observed class/method catalogue', '',
          'Every saved stack frame and catch location, grouped by lane. Native names are retained.',
          'BOUND-MATCH means constant-pool and method byte hashes match a frozen class file.',
          'UNBOUND means absent from that catalogue, including frames r10 did not require checking.',
          'Categories inferred from names are inventory labels, not trusted runtime provenance.',
          'Generated names are not attributed to a host merely by stripping a suffix.', '']
    for lane in ('oracle', 'postgresql'):
        md += ['## ' + lane, '']
        for cat in sorted({r['category'] for r in all_rows if r['lane'] == lane}):
            md += ['### ' + cat, '', '| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |',
                   '|---|---|---|---|---|']
            for r in all_rows:
                if r['lane'] == lane and r['category'] == cat:
                    md.append('| `' + r['class'] + '` | `' + r['method'] + r['signature'] + '` | '
                              + r['binding'] + ' | ' + ('required' if r['r10_check_required'] else 'not required')
                              + ' | ' + str(r['stack_occurrences']) + ' / ' + str(r['catch_occurrences']) + ' |')
            md.append('')
    (out / 'observed-frames.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
