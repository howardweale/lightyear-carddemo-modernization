"""One bounded, real-JDI host experiment. Saves local raw output; publishes metadata only."""
from tools.b06_host_probe.jdk import executable
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from tools.ms94_b06_observer_audit import Audit


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def run(jdk, out, threads=4, iterations=800, depth=128, timeout=600, observer_heap_mib=192):
    if type(observer_heap_mib) is not int or not 32 <= observer_heap_mib <= 4096:
        raise ValueError('stress observer heap out of range')
    if threads < 3 or iterations < 100 or depth <= 100: raise ValueError('stress scope too small')
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    source = root/'factory/idempiere/b06-observer/PostingObserver.java'
    fixture = root/'tests/fixtures/B06GenerationStress.java'
    java = executable(jdk,'java'); javac = executable(jdk,'javac')
    subprocess.run([str(javac), '--add-modules', 'jdk.jdi', '-d', str(out), str(source), str(fixture)],
                   check=True, capture_output=True, timeout=60)
    version = subprocess.run([str(java), '-version'], capture_output=True, text=True, check=True).stderr
    started = time.time(); timed_out = False
    with (out/'target.stderr').open('w') as target_error, (out/'observer.stdout').open('w') as output, (out/'observer.stderr').open('w') as error:
        target = subprocess.Popen([str(java), '-Xss4m', '-Djava.lang.invoke.MethodHandle.CUSTOMIZE_THRESHOLD=0',
            '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0',
            '-cp', str(out), 'fixture.B06GenerationStress', str(threads), str(iterations), str(depth),
            str(out/'fixture/StressHidden.class')], stdout=subprocess.PIPE, stderr=target_error, text=True)
        try:
            banner = target.stdout.readline(); port = banner.strip().rsplit(':', 1)[-1].strip()
            if not port.isdigit(): raise ValueError('host listener unavailable')
            observer = subprocess.Popen([str(java), '-Xmx%dm' % observer_heap_mib, '--add-modules', 'jdk.jdi', '-cp', str(out),
                'lightyear.observer.PostingObserver', '127.0.0.1', port, 'observer-binding-v2'],
                stdin=subprocess.DEVNULL, stdout=output, stderr=error)
            try: observer.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True; observer.terminate(); observer.wait(timeout=15)
            if observer.returncode == 0:
                target_output, _ = target.communicate(timeout=30)
            else:
                target.terminate(); target_output, _ = target.communicate(timeout=15)
        finally:
            if target.poll() is None: target.terminate(); target.wait(timeout=15)
    (out/'target.stdout').write_text(target_output)
    elapsed = time.time() - started
    counts = Counter(); entries = defaultdict(Counter); depths = defaultdict(lambda: [1000000, 0])
    audit = Audit(); audit_error = None; previous = None; refusal_context = None
    intervals = {}; thread_switches = 0; previous_thread = None
    with (out/'observer.stdout').open() as stream:
        for line in stream:
            event = json.loads(line); counts[event['kind']] += 1
            if event['kind'] == 'generation-entry':
                record = event['record']; thread = str(record['thread_id'])
                entries[thread][record['entry_method']] += 1
                intervals.setdefault(thread, [event['sequence'], event['sequence']])[1] = event['sequence']
                if previous_thread is not None and previous_thread != thread: thread_switches += 1
                previous_thread = thread
                depths[thread][0] = min(depths[thread][0], record['entry_depth'])
                depths[thread][1] = max(depths[thread][1], record['entry_depth'])
            if event['kind'] == 'observer-audit':
                try: audit.event(event)
                except ValueError as exc: audit_error = str(exc)
                if event['action'] == 'dispatch-refused': refusal_context = previous
            previous = event
    complete = False
    try: audit.complete(); complete = audit_error is None
    except ValueError as exc: audit_error = audit_error or str(exc)
    stderr = (out/'observer.stderr').read_text()
    deep_workers = [t for t in entries if depths[t][0] > 100 and
        any('InvokerBytecodeGenerator.' in method for method in entries[t]) and
        any('ClassDefiner.defineClass' in method for method in entries[t]) and
        sum(n for method, n in entries[t].items() if 'spinInnerClass' in method) >= iterations]
    stress_completed = (not timed_out and observer.returncode == target.returncode == 0 and complete and
        target_output.strip() == 'completed_iterations=' + str(threads * iterations) and
        len(deep_workers) == threads and counts['generation-entry'] ==
        counts['generation-return'] + counts['generation-unwind'])
    result = dict(schema='b06-host-generation-stress/1', host_only=True, model_calls=0,
        started_at_utc=datetime.fromtimestamp(started, timezone.utc).isoformat(),
        finished_at_utc=datetime.now(timezone.utc).isoformat(), stress_completed=stress_completed,
        native_admission=False, observer_sha256=sha(source), fixture_sha256=sha(fixture),
        java_version=version, threads=threads, requested_iterations_per_thread=iterations,
        requested_recursive_depth=depth, method_handle_customize_threshold=0,
        observer_heap_mib=observer_heap_mib, elapsed_seconds=round(elapsed, 3), timeout_seconds=timeout, timed_out=timed_out,
        observer_returncode=observer.returncode, target_returncode=target.returncode,
        target_completion=target_output.strip(), counts=dict(counts), audit_complete=complete,
        audit_error=audit_error, generation_methods_by_thread=dict(entries), depth_ranges=dict(depths),
        covered_deep_workers=deep_workers, entry_sequence_intervals=intervals, generation_thread_switches=thread_switches,
        compiled_observer_classes_sha256={p.relative_to(out).as_posix(): sha(p)
            for p in sorted((out/'lightyear/observer').glob('PostingObserver*.class'))},
        duplicate_return_arm='duplicate return arm' in stderr,
        unmatched_activation='generation return arm without matching activation' in stderr,
        observer_stderr=stderr, refusal_context=refusal_context,
        output_hashes={name: sha(out/name) for name in ('observer.stdout','observer.stderr','target.stdout','target.stderr')})
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--jdk', type=Path, required=True); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=800)
    parser.add_argument('--observer-heap-mib', type=int, default=192)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    run(args.jdk, args.out, iterations=args.iterations, timeout=args.timeout, observer_heap_mib=args.observer_heap_mib)
