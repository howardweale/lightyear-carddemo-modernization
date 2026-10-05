"""Offline source compilation for a hash-bound catalog; never runs tests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    inputs, output = Path('/sources'), Path('/results')
    specification = json.loads((inputs / 'sources.json').read_bytes())
    target = Path('/application/org.idempiere.test/src/org/idempiere/test/LightyearOperationsTest.java')
    compiled_root = Path('/application/org.idempiere.test/target')
    results = []
    for item in specification['sources']:
        source = inputs / item['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item['sha256']
        folder = output / item['sha256']; folder.mkdir(exist_ok=False)
        # Remove only previously compiled control classes, so absent output cannot
        # be mistaken for this source's successful compilation.
        for path in compiled_root.rglob('*.class'):
            if path.name.startswith(('LightyearOperationsTest', 'JourneySupport', 'B06OutsideControl')):
                path.unlink()
        shutil.copyfile(source, target)
        started = time.monotonic()
        args = ['mvn', '-o', '-B', 'test-compile', '-DskipTests=true', '-Dmaven.test.skip=false',
                '-DmaterializeProduct=none', '-DassembleRepository=none']
        with (folder / 'compiler.log').open('xb') as stream:
            result = subprocess.run(args, cwd='/application', stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=1200)
        classes = []
        for path in sorted(compiled_root.rglob('*.class')):
            if path.name.startswith(('LightyearOperationsTest', 'JourneySupport', 'B06OutsideControl')):
                raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
                (folder / (sha + '.class')).write_bytes(raw)
                classes.append({'origin': str(path), 'sha256': sha})
        record = {**item, 'exit_code': result.returncode, 'classes': classes,
                  'elapsed_seconds': round(time.monotonic()-started, 3), 'command': args,
                  'model_calls': 0, 'tests_run': 0, 'native_pairs': 0}
        (folder / 'compilation.json').write_text(json.dumps(record, sort_keys=True, indent=2), encoding='utf-8')
        results.append(record)
        print(json.dumps({'source': item['sha256'], 'exit_code': result.returncode,
                          'classes': len(classes), 'elapsed_seconds': record['elapsed_seconds']}), flush=True)
        # A compiler failure stays preserved; no corrected source is substituted.
        # Each distinct source is a preparation input, not a qualification slot.
        # Collect all compile outcomes; never retry or change a source here.
    (output / 'compilations.json').write_text(json.dumps(results, sort_keys=True, indent=2), encoding='utf-8')
    assert len(results) == len(specification['sources']) and all(r['exit_code'] == 0 for r in results)


if __name__ == '__main__': main()
