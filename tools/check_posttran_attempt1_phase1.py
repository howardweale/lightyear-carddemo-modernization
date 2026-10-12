"""One retained POSTTRAN attempt: Java21 compile, structure and invariants only.
No model calls, legacy twin executions/comparisons or unresolved-register writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java'
EXPECTED = '1b501ff62f1578064d6867c18ad1a0a412d8d7c6e91bb82c91d52bb538134186'
OUTPUTS = {'ACCTFILE': 300, 'TCATBALF': 50, 'TRANFILE': 350, 'DALYREJS': 430}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def structural(folder):
    from lightyear_mainframe.records import load_copybook, from_ascii_fixed
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
    images = {}
    for dd in OUTPUTS:
        path = folder / dd
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing-or-linked-output:' + dd)
        raw = path.read_bytes()
        layout = load_copybook(ROOT / dataset_binding(load_bindings(), 'POSTTRAN', 'STEP15', dd)['copybook'])
        from_ascii_fixed(layout, raw)
        raw.decode('ascii')
        images[dd] = raw
        for suffix in ('.txt', '.bin'):
            alias = folder / (dd + suffix)
            if alias.exists() and (alias.is_symlink() or alias.read_bytes() != raw):
                raise ValueError('output-alias-disagrees:' + dd)
    return images


def policy(inputs, outputs, classes):
    def path(p):
        return p.resolve().as_posix()
    return '\n'.join([
        'grant {',
        f'permission java.io.FilePermission "{path(classes)}/-", "read";',
        f'permission java.io.FilePermission "{path(inputs)}", "read";',
        f'permission java.io.FilePermission "{path(inputs)}/-", "read";',
        f'permission java.io.FilePermission "{path(outputs)}", "read,write";',
        f'permission java.io.FilePermission "{path(outputs)}/-", "read,write";',
        'permission java.util.PropertyPermission "*", "read";',
        'permission java.lang.RuntimePermission "exitVM.*";',
        '};',
    ])


def limits():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024**2, 32 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))


def run(output):
    # Attempt 1 was consumed on the original CI head. Publication/lint changes
    # must never silently compile or execute it again.
    frozen = ROOT / 'docs/factory/posttran-attempt1-phase1-2026-10-12.json'
    if frozen.exists():
        raw = frozen.read_bytes()
        if sha(raw) != 'd77d29ccea6c933ad242ec7e88024b0a3a18d7eeaaadde6345a691b244b16321' or sha(CANDIDATE.read_bytes()) != EXPECTED:
            raise ValueError('consumed-attempt-binding-changed')
        record = json.loads(raw)
        if record['head'] != 'f9eeccaa19ed137f8250baa8594831e8dc7dbd90' or record['candidate_sha256'] != EXPECTED:
            raise ValueError('consumed-attempt-head-mismatch')
        output.mkdir(parents=True, exist_ok=False)
        (output/'report.json').write_bytes(raw)
        print('Attempt 1 already consumed in run 38295068434; historical result only, no compile or execution on this head.')
        return record
    if os.name != 'posix':
        raise ValueError('CI Linux required; no local candidate execution')
    if sha(CANDIDATE.read_bytes()) != EXPECTED:
        raise ValueError('candidate-bytes-changed')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = dict(schema='posttran-phase1-gate/1', attempt=1, candidate_sha256=EXPECTED,
                  head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  compile_attempts=1, model_calls=0, twin_comparisons=0, phase2_authorized=False,
                  unresolved_register_written=False, cases=[], passed=False)
    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    save()  # consume this compile before invocation; never retry in this process
    classes = output/'classes'; classes.mkdir()
    try:
        version=subprocess.run(['javac','-version'],capture_output=True,text=True,check=True).stdout.strip()
        if not re.match(r'javac 21(?:\.|$)',version):raise ValueError('Java21-required')
        report['compiler']=version
        result=subprocess.run(['javac','-proc:none','--release','21','-d',str(classes),str(CANDIDATE)],capture_output=True,timeout=120)
        (output/'compile.stdout').write_bytes(result.stdout);(output/'compile.stderr').write_bytes(result.stderr)
        report['compile_returncode']=result.returncode;save()
        if result.returncode:return report
        report['class_hashes']={p.relative_to(classes).as_posix():sha(p.read_bytes()) for p in sorted(classes.rglob('*.class'))}
        from lightyear_mainframe.legacy_twin import public_inputs
        from lightyear_mainframe.scenario_generation import case
        from lightyear_mainframe.posttran_invariants import check
        manifest=json.loads((ROOT/'docs/factory/posttran-second-opinion/generated-input-manifest.json').read_text())['scenarios']
        names=['posttran-public','posttran-missing-card','posttran-missing-account','posttran-expired-account']+sorted(manifest)
        for ordinal,name in enumerate(names):
            if time.monotonic()-started>=7200:raise ValueError('phase1-two-hour-budget')
            _,meta,images,_=case(name) if name in manifest else public_inputs(name)
            before={dd:sha(raw) for dd,raw in images.items()}
            if name in manifest and before!=manifest[name]['input_sha256']:raise ValueError('preregistered-input-changed:'+name)
            row=dict(case=name,input_sha256=before,runs=[],passed=False);report['cases'].append(row)
            for repeat in (1,2):
                base=output/f'{ordinal:02d}-{repeat}';inputs=base/'input';dest=base/'output'
                inputs.mkdir(parents=True);dest.mkdir()
                for dd,raw in images.items():(inputs/dd).write_bytes(raw)
                pol=base/'candidate.policy';pol.write_text(policy(inputs,dest,classes))
                command=['java','-Xmx512m','-Djava.security.manager','-Djava.security.policy=='+str(pol.resolve()),'-cp',str(classes.resolve()),'PosttranCandidate',str(inputs.resolve()),str(dest.resolve()),meta['candidate_timestamp']]
                attempt={'repeat':repeat}
                row['runs'].append(attempt)
                try:
                    begin=time.monotonic()
                    child=subprocess.run(command,cwd=base,capture_output=True,timeout=20,preexec_fn=limits,
                        env={k:v for k,v in os.environ.items() if k in ('PATH','JAVA_HOME','LANG')})
                    (base/'stdout').write_bytes(child.stdout);(base/'stderr').write_bytes(child.stderr)
                    attempt.update(process_returncode=child.returncode,elapsed_seconds=time.monotonic()-begin,stdout_sha256=sha(child.stdout),stderr_sha256=sha(child.stderr))
                    if {p.name:sha(p.read_bytes()) for p in inputs.iterdir()}!=before:raise ValueError('input-modified')
                    after=structural(dest)
                    code_text=(dest/'RETURN-CODE').read_text().strip()
                    if not re.fullmatch(r'[0-9]{1,4}',code_text):raise ValueError('invalid-source-returncode')
                    code=int(code_text)
                    if child.returncode!=code%256:raise ValueError('process-source-returncode-disagree')
                    invariant=check(images,after,timestamp=meta['candidate_timestamp'],returncode=code)
                    attempt.update(source_returncode=code,outputs_sha256={dd:sha(raw) for dd,raw in after.items()},
                        invariant_passed=invariant['passed'],failures=invariant['failures'],structural_passed=True)
                except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
                    attempt.update(structural_passed=False,error=str(exc))
                save()
            a,b=row['runs'];row['repeatable']=all(a.get(k) is not None and a.get(k)==b.get(k) for k in ('outputs_sha256','source_returncode','stdout_sha256'))
            row['passed']=row['repeatable'] and all(r.get('structural_passed') and r.get('invariant_passed') for r in row['runs'])
            save()
        report['passed']=all(r['passed'] for r in report['cases']) and len(report['cases'])==18
        report['disagreement_handling']='Preserve Phase1 diagnostics only; no unresolved-register additions or Phase2 comparison.'
    except Exception as exc:
        report['gate_error']=str(exc)
    finally:save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.output.resolve());print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
