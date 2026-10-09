"""Host-only public fixture exercising the production observer, not native admission.

No Docker, model, database, signer or target method invocation. The acknowledgement
sink authorizes no SQL assertion: results are explicitly host fixture evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time


def run(java, classes, output, timeout=120, no_cds=False):
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    target_args = [str(java), *(['-Xshare:off'] if no_cds else []), '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:'+str(port),
                   '-cp', str(classes), 'org.idempiere.test.LightyearOperationsTest']
    observer_args = [str(java), '--add-modules', 'jdk.jdi', '-cp', str(classes),
                     'lightyear.observer.PostingObserver', '127.0.0.1', str(port), 'observer-binding-v2']
    target = observer = None; started = time.monotonic(); records = []; error = None
    with (out/'target.stdout').open('wb') as stdout, (out/'target.stderr').open('wb') as stderr, (out/'observer.stderr').open('wb') as observer_err:
        try:
            target = subprocess.Popen(target_args, stdout=stdout, stderr=stderr)
            # The suspended JVM reports its listener before the collector attaches.
            while b'Listening for transport dt_socket' not in (out/'target.stdout').read_bytes():
                if target.poll() is not None or time.monotonic()-started > 15:
                    raise RuntimeError('host-target-listener-unavailable')
                time.sleep(.05)
            observer = subprocess.Popen(observer_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=observer_err)
            q = queue.Queue()
            def read():
                for line in observer.stdout: q.put(line)
                q.put(None)
            reader = threading.Thread(target=read, daemon=True); reader.start()
            with (out/'events.jsonl').open('xb') as log:
                while True:
                    remaining = timeout-(time.monotonic()-started)
                    if remaining <= 0: raise TimeoutError('host-observer-deadline')
                    line = q.get(timeout=remaining)
                    if line is None: break
                    log.write(line); log.flush()
                    event = json.loads(line); records.append(event)
                    if event['checkpoint']:
                        observer.stdin.write((str(event['sequence'])+'\n').encode()); observer.stdin.flush()
            if observer.wait(timeout=5) != 0: raise RuntimeError('host-observer-failed')
            if target.wait(timeout=5) != 0: raise RuntimeError('host-target-failed')
            if not records or records[-1]['kind'] != 'vm-death': raise RuntimeError('host-incomplete-lifecycle')
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        finally:
            for child in (observer, target):
                if child is not None and child.poll() is None:
                    child.kill(); child.wait(timeout=10)
    report = {'schema':'b06-observer-v2-host-capture/1', 'complete':error is None, 'error':error,
              'elapsed_seconds':round(time.monotonic()-started,3), 'events':len(records),
              'checkpoints':sum(r['checkpoint'] for r in records),
              'model_calls':0, 'docker_commands':0, 'native_pairs':0, 'target_method_invocations':0,
              'observer_class_files_sha256':{p.relative_to(Path(classes)).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((Path(classes)/'lightyear/observer').glob('*.class'))},
              'fixture_class_files_sha256':{p.relative_to(Path(classes)).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((Path(classes)/'org').rglob('*.class'))},
              'observer_sha256':hashlib.sha256((Path(classes)/'lightyear/observer/PostingObserver.class').read_bytes()).hexdigest(),
              'java_sha256':hashlib.sha256(Path(java).read_bytes()).hexdigest(),
              'events_sha256':hashlib.sha256((out/'events.jsonl').read_bytes()).hexdigest(),
              'no_cds_experiment':no_cds, 'target_arguments':target_args,
              'claim':'Public host fixture, no database readback or native qualification'}
    (out/'report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--java',required=True);parser.add_argument('--classes',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--no-cds',action='store_true')
    a=parser.parse_args();result=run(a.java,a.classes,a.output,no_cds=a.no_cds);print(json.dumps(result));raise SystemExit(0 if result['complete'] else 1)
