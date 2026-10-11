"""Host-only memory baseline; production observer source is compiled unchanged.

Raw evidence and heap histograms stay in a fresh local directory. The reflection
harness supplies only instrumentation and explicit return-loss fault injection.
It is not native evidence, a complete provenance replay, or approval to run.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from tools.b06_host_probe.jdk import executable


def stacks_source():
    """3000 distinct public-fixture classes across thirty 100-class stacks."""
    lines = ['package fixture;', 'public class MemoryStacks {',
             'public static void walk(int group,B06GenerationStress.Work work)throws Throwable {',
             'switch(group){']
    for group in range(30):
        lines.append(f'case {group}: MemoryStack{group*100}.walk(work);break;')
    lines += ['default:throw new IllegalArgumentException();}}}']
    for number in range(3000):
        call = 'work.run()' if number % 100 == 99 else f'MemoryStack{number+1}.walk(work)'
        # About 1 KiB of method bytecode, near the captured definition-input median.
        # Public arithmetic only, with larger public outliers to exercise copying.
        padding = 256 if number % 100 else 2048
        body = ''.join(f'x+={1+i%300};' for i in range(padding))
        lines.append(f'class MemoryStack{number} {{ static void walk(B06GenerationStress.Work work)throws Throwable{{{call};}} '
                     f'static int payload(int x){{{body}return x;}} }}')
    lines.append('class MemoryHidden { public static int value(){return 7;} '
                 'public static int payload(int x){' + ''.join(f'x+={i};' for i in range(256)) + 'return x;} }')
    return '\n'.join(lines)+'\n'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def run(jdk, out, *, iterations=1400, timeout=10800, heap=192, suppress_every=200):
    if heap != 192 or iterations < 1400 or not 100 <= suppress_every <= 1000:
        raise ValueError('native-volume-baseline-scope')
    if not 60 <= timeout <= 3*24*3600:
        raise ValueError('memory-probe-time-budget')
    jdk, out = Path(jdk), Path(out)
    java, javac, jcmd = (executable(jdk, name) for name in ('java', 'javac', 'jcmd'))
    root = Path(__file__).resolve().parents[2]
    source = root/'factory/idempiere/b06-observer/PostingObserver.java'
    fixture = root/'tests/fixtures/B06GenerationStress.java'
    harness = root/'tools/b06_host_probe/MemoryObserverHarness.java'
    out.mkdir(parents=True, exist_ok=False)
    classes = out/'classes'; classes.mkdir()
    generated = out/'MemoryStacks.java'; generated.write_text(stacks_source(), encoding='utf-8')
    with (out/'compile.stdout').open('w') as stdout, (out/'compile.stderr').open('w') as stderr:
        subprocess.run([str(javac), '-J-Xmx512m', '--add-modules', 'jdk.jdi', '-d', str(classes),
                        str(source), str(fixture), str(harness), str(generated)],
                       check=True, stdout=stdout, stderr=stderr, timeout=180)
    manifest = dict(schema='b06-memory-baseline/1', host_only=True, native_admission=False,
                    observer_source_sha256=digest(source), harness_sha256=digest(harness),
                    fixture_sha256=digest(fixture), generated_fixture_sha256=digest(generated),
                    threads=3, iterations_per_thread=iterations, minimum_requested_generation_calls=3*3*iterations,
                    observer_mode='diagnostic-unmatched-return-v1',
                    distinct_stack_fixture_classes=3000, stack_fixture_depth=100, observer_heap_mib=heap,
                    suppression_eligible_return_interval=suppress_every, timeout_seconds=timeout,
                    model_calls=0, qualification_credit=False,
                    compiled_observer_sha256={p.name:digest(p) for p in (classes/'lightyear/observer').glob('*.class')})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    started = time.monotonic(); timed_out = False; observer = None
    with (out/'target.stderr').open('wb') as terr, (out/'observer.stdout').open('wb') as output, (out/'observer.stderr').open('wb') as error:
        target = subprocess.Popen([str(java), '-Xmx512m', '-Xss4m', '-Djava.lang.invoke.MethodHandle.CUSTOMIZE_THRESHOLD=0',
            '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0', '-cp', str(classes),
            'fixture.B06GenerationStress','3',str(iterations),'100',str(classes/'fixture/MemoryHidden.class'),'native-volume'],
            stdout=subprocess.PIPE, stderr=terr, text=True)
        try:
            banner = target.stdout.readline(); port = banner.strip().rsplit(':',1)[-1].strip()
            if not port.isdigit():
                raise ValueError('host-listener-unavailable')
            observer = subprocess.Popen([str(java), '-Xmx192m', '-XX:+HeapDumpOnOutOfMemoryError',
                '-XX:HeapDumpPath='+str(out/'observer-private.hprof'), '--add-modules','jdk.jdi', '-cp',str(classes),
                'MemoryObserverHarness','127.0.0.1',port,str(out),str(jcmd),str(suppress_every)],
                stdin=subprocess.DEVNULL, stdout=output, stderr=error)
            (out/'processes.json').write_text(json.dumps({'host_target_pid':target.pid,'host_observer_pid':observer.pid})+'\n')
            try:
                observer.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True;observer.terminate();observer.wait(timeout=30)
            if observer.returncode != 0:
                target.terminate()
            target_stdout, _ = target.communicate(timeout=30)
        finally:
            if observer and observer.poll() is None:
                observer.terminate(); observer.wait(timeout=30)
            if target.poll() is None:
                target.terminate(); target.wait(timeout=30)
    (out/'target.stdout').write_text(target_stdout, encoding='utf-8')
    with (out/'heap.csv').open() as f:
        samples = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(f)]
    stderr = (out/'observer.stderr').read_text(errors='replace')
    result = dict(manifest, observer_returncode=observer.returncode, target_returncode=target.returncode,
                  elapsed_seconds=round(time.monotonic()-started,3), timed_out=timed_out,
                  oom_reproduced='java.lang.OutOfMemoryError: Java heap space' in stderr,
                  heap_samples=samples, sample_peak=max((r['heap_used_after_gc'] for r in samples),default=0),
                  workload_completed=(out/'completed.txt').exists(),
                  output_sha256={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.suffix!='.hprof'})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('oom_reproduced','workload_completed','elapsed_seconds','sample_peak','timed_out')}))
    return result
