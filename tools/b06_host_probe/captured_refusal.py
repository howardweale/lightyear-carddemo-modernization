"""Authenticate and minimize the diagnostic refusal; never invent a missing entry."""
from tools.b06_host_probe.jdk import executable
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from lightyear_calibration.contracts import canonical, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_observer_audit import Audit


def signed(value, key):
    if not verify_envelope(value, key):
        raise ValueError('invalid signature')
    verify({k: v for k, v in value.items() if k != 'signature'})


def derive(folder, key):
    folder = Path(folder)
    census = json.loads((folder/'frame-census.json').read_bytes())
    failure = json.loads((folder/'failure.json').read_bytes())
    for v in (census, failure): signed(v, key)
    if census['complete'] or failure['complete']: raise ValueError('not a failed prefix')
    audit = Audit(); previous = None; digest = hashlib.sha256(); counts = Counter()
    histories = {}; pending = {}; last_jdi = None; refused = None
    for index, line in enumerate((folder/'events.jsonl').open('rb'), 1):
        digest.update(line); row = json.loads(line); verify(row); e = row['event']
        if row['previous_sha256'] != previous or e['sequence'] != index:
            raise ValueError('event chain differs')
        previous = row['content_sha256']; kind = e['kind']; counts[kind] += 1
        if kind == 'observer-audit':
            audit.event(e)
            if e['action'] == 'jdi-event':
                last_jdi = e; d = e['detail']; thread = d.get('thread_id')
                if thread is not None:
                    # A closed structural export. No arguments, values, names or blobs.
                    keep = ('event_type','request_id','depth','location','top_location',
                            'selected_generation','return_breakpoint','catch_breakpoint','pending','arm')
                    item = {k:d[k] for k in keep if k in d}
                    histories.setdefault(thread, []).append(dict(sequence=index,kind='jdi-event',
                        event_set_id=e['event_set_id'],event_position=e['event_position'],detail=item))
                    if d['pending'] != list(reversed(pending.get(thread, []))):
                        raise ValueError('recorded pending differs from reconstructed lifecycles')
            elif e['action'] == 'dispatch-refused':
                if last_jdi is None: raise ValueError('missing refusal context')
                refused = dict(event_sequence=last_jdi['sequence'], refusal_sequence=index,
                    thread=last_jdi['detail']['thread_id'], exception_class=e['detail']['exception_class'])
        elif kind in ('generation-entry','generation-return','generation-unwind'):
            r=e['record']; thread=r['thread_id']; call=dict(generation_id=r['generation_id'],
                method=r['entry_method'],depth=r['entry_depth'])
            stack=pending.setdefault(thread, [])
            if kind == 'generation-entry': stack.append(call)
            elif not stack or stack.pop() != call: raise ValueError('generation lifecycle differs')
            histories.setdefault(thread, []).append(dict(sequence=index,kind=kind,**call))
    if not refused or not audit.refused: raise ValueError('no recorded refusal')
    if (digest.hexdigest()!=census['event_file_sha256'] or index!=census['event_count'] or
        index!=failure['event_count'] or previous!=census['last_event_sha256'] or
        previous!=failure['last_event_sha256'] or census['plan_sha256']!=failure['plan_sha256']):
        raise ValueError('signed commitment differs')
    rows=histories[refused['thread']]
    for row in rows:
        names = ([row['method']] if row['kind']!='jdi-event' else
                 [row['detail'][k]['class'] for k in ('location','top_location') if k in row['detail']])
        if any(not n.startswith('java.lang.') for n in names):
            raise ValueError('public fixture contains non-JDK location')
    return dict(schema='b06-captured-refusal/1',source_event_sha256=digest.hexdigest(),
        census_sha256=census['content_sha256'],failure_sha256=failure['content_sha256'],
        event_count=index,counts=dict(counts),audit_records=audit.count,**refused,
        thread_events=rows,remaining_open_calls=sum(map(len,pending.values())),
        target_jvm_executed=False,tracker_fix_proven=False,native_credit=False)


def reproduce(fixture, source, jdk):
    """Run the real Java guard against its captured operands, no target JVM/JDI session."""
    e=fixture['thread_events'][-1]; d=e['detail']
    if (e['sequence']!=fixture['event_sequence'] or d['event_type']!='breakpoint' or
        not d['return_breakpoint'] or not d['selected_generation'] or d['pending'] or 'arm' in d or
        d['location']!=d['top_location']):
        raise ValueError('fixture is not the captured empty-pending return refusal')
    loc=d['location']; source=Path(source); jdk=Path(jdk)
    probe=Path(__file__).with_name('CapturedReturnProbe.java')
    with tempfile.TemporaryDirectory(prefix='b06-captured-guard-') as tmp:
        compiled=subprocess.run([str(executable(jdk,'javac')),'--add-modules','jdk.jdi','-d',tmp,
            str(source),str(probe)],capture_output=True,text=True,timeout=60)
        if compiled.returncode: raise ValueError(compiled.stderr)
        result=subprocess.run([str(executable(jdk,'java')),'--add-modules','jdk.jdi','-cp',tmp,
            'CapturedReturnProbe',loc['class'],loc['method'],loc['signature'],str(fixture['thread']),
            str(d['depth']),str(loc['code_index'])],capture_output=True,text=True,timeout=30)
        expected='java.lang.IllegalStateException: generation return arm without matching activation'
        if result.returncode or result.stdout.strip()!=expected: raise ValueError(result.stdout+result.stderr)
    return dict(exact_guard_exception_reproduced=True,event_sequence=fixture['event_sequence'],
        refusal_sequence=fixture['refusal_sequence'],exception=expected,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fixture_sha256=hashlib.sha256(canonical(fixture)+b'\n').hexdigest(),
        scheduling_cause_proven=False,tracker_fix_proven=False,target_jvm_executed=False,
        docker_commands=0,model_calls=0,native_credit=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--public-key',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--jdk',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--result',type=Path,required=True)
    a=p.parse_args();fixture=derive(a.folder,a.public_key.read_bytes());result=reproduce(fixture,a.source,a.jdk)
    with a.fixture.open('xb') as f:f.write(canonical(fixture)+b'\n')
    with a.result.open('xb') as f:f.write(canonical(result)+b'\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
