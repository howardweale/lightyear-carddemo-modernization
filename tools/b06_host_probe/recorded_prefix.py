"""Authenticate failed native prefixes and export structural, value-free diagnostics.

No JVM, Docker, target, private key, replay gate, or original-evidence writes.
Successful collector events are not raw JDI traffic: absent events stay absent.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from lightyear_calibration.contracts import canonical, verify
from lightyear_control_tower.decisions import verify_envelope


def derive(folder, public_key):
    folder = Path(folder)
    census = json.loads((folder / 'frame-census.json').read_bytes())
    failure = json.loads((folder / 'failure.json').read_bytes())
    for record in (census, failure):
        if not verify_envelope(record, public_key):
            raise ValueError('invalid signed prefix commitment')
    if census['complete'] or failure['complete']:
        raise ValueError('expected failed prefix')
    previous = None
    file_hash = hashlib.sha256()
    counts = Counter()
    open_calls = defaultdict(list)
    rows = []
    mismatches = []
    with (folder / 'events.jsonl').open('rb') as stream:
        for index, line in enumerate(stream, 1):
            file_hash.update(line)
            item = json.loads(line)
            verify(item)
            event = item['event']
            if item['previous_sha256'] != previous or event['sequence'] != index:
                raise ValueError('invalid event chain')
            previous = item['content_sha256']
            kind = event['kind']
            counts[kind] += 1
            if kind not in ('generation-entry', 'generation-return', 'generation-unwind'):
                continue
            r = event['record']
            row = dict(index=index, kind=kind, thread=r['thread_id'],
                       method=r['entry_method'], depth=r['entry_depth'])
            # Only structural call sites, never bytecode, arguments, object graphs,
            # business values, paths, class blobs or candidate return values.
            row['stack'] = [dict(class_name=f['class'], method=f['method'],
                                 signature=f['signature'], code_index=f['code_index'])
                            for f in r.get('stack', [])]
            if kind == 'generation-unwind':
                row['catch_depth'] = event['catch_depth']
                row['exception_class'] = event['exception_class']
            calls = open_calls[row['thread']]
            if kind == 'generation-entry':
                calls.append(row)
            elif not calls or (calls[-1]['method'], calls[-1]['depth']) != (row['method'], row['depth']):
                mismatches.append(index)
            else:
                row['entry_index'] = calls.pop()['index']
            rows.append(row)
    if (file_hash.hexdigest() != census['event_file_sha256'] or
            index != census['event_count'] or index != failure['event_count'] or
            previous != census['last_event_sha256'] or previous != failure['last_event_sha256'] or
            census['plan_sha256'] != failure['plan_sha256']):
        raise ValueError('prefix commitment differs')
    return dict(schema='b06-structural-prefix/1', source_event_sha256=file_hash.hexdigest(),
                census_sha256=census['content_sha256'], failure_sha256=failure['content_sha256'],
                event_count=index, counts=dict(counts), events=rows,
                pairing_mismatches=mismatches,
                open_calls={str(k): v for k, v in open_calls.items() if v},
                missing_fields=['failing JDI event', 'ARETURN arm traffic', 'request identity',
                                'event-set identity/order', 'live return stack/location',
                                'thread name', 'VM suspend/resume traffic'],
                exact_exception_reproducible=False, model_calls=0, native_credit=False)


def structural_fixture(result, source_commit, source_sha256):
    """Closed export: selected JDK methods only, no full stacks or business fields."""
    methods = sorted({e['method'] for e in result['events']})
    if any(not m.startswith(('java.lang.ClassLoader.', 'java.lang.invoke.')) for m in methods):
        raise ValueError('non-JDK generation method')
    return dict(schema='b06-generation-prefix-fixture/1', source_commit=source_commit,
                source_sha256=source_sha256, source_event_sha256=result['source_event_sha256'],
                census_sha256=result['census_sha256'], failure_sha256=result['failure_sha256'],
                counts=result['counts'], event_count=result['event_count'], methods=methods,
                # No arms, exits, exceptions or event-set ordering are invented.
                events=[[e['index'], e['kind'], e['thread'], methods.index(e['method']), e['depth']]
                        for e in result['events']], missing_fields=result['missing_fields'])


def replay_projection(fixture):
    """Replay only the pending-stack operations common to the two pinned sources.

    This is NOT execution of Java or an emulation of unrecorded JDI requests.
    Native atReturn() runs before emit(); its failure event cannot be reconstructed.
    """
    pending = defaultdict(list)
    previous = 0
    for index, kind, thread, method, depth in fixture['events']:
        if index <= previous or index > fixture['event_count'] or depth < 1:
            raise ValueError('invalid structural event order/depth')
        previous = index
        call = (method, depth)
        if kind == 'generation-entry':
            pending[thread].append((index, call))
        elif kind == 'generation-return':
            if not pending[thread] or pending[thread][-1][1] != call:
                raise ValueError('recorded generation return mismatch')
            pending[thread].pop()
        else:
            raise ValueError('unsupported structural kind')
    return dict(recorded_pairing_passed=True, exact_exception_reproduced=False,
                unrecorded_failure_event_index=None, tracker_fix_proven=False,
                missing_fields=fixture['missing_fields'],
                open_calls={str(t): [{'entry_index': i, 'method': fixture['methods'][c[0]],
                                      'depth': c[1]} for i, c in calls]
                            for t, calls in pending.items() if calls})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--public-key', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    result = derive(args.folder, args.public_key.read_bytes())
    with args.out.open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('events', 'open_calls')}))
    print(json.dumps({'open_calls': {k: [{q: r[q] for q in ('index', 'method', 'depth')}
                                        for r in v] for k, v in result['open_calls'].items()}}))


if __name__ == '__main__':
    main()
