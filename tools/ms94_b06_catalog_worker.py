"""Offline pinned-image inspection; no database, test, application or model run."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

TARGETS = ('org/compiere/acct/Doc', 'org/compiere/acct/DocManager',
           'org/compiere/model/PO', 'org/compiere/util/DB',
           'org/idempiere/test/JourneySupport', 'org/idempiere/test/LightyearOperationsTest')
PREFIXES = ('org/junit/', 'org/opentest4j/', 'junit/framework/')


def wanted(name):
    return name.endswith('.class') and (name.startswith(PREFIXES) or
        any(name == target + '.class' or name.startswith(target + '$') for target in TARGETS))


def main():
    out = Path('/results')
    subprocess.run(['javac', '--add-modules', 'jdk.jdi', '-g', '-d', str(out / 'observer'),
                    '/source/PostingObserver.java'], check=True, timeout=180)
    items = []
    def save(origin, member, raw):
        sha = hashlib.sha256(raw).hexdigest()
        target = out / 'class-bytes' / (sha + '.class')
        if not target.exists(): target.write_bytes(raw)
        items.append({'origin': origin, 'member': member, 'sha256': sha})
    (out / 'class-bytes').mkdir()
    jars = set()
    for base in (Path('/application'), Path('/root/.m2')):
        if not base.exists(): continue
        for path in sorted(base.rglob('*')):
            if not path.is_file(): continue
            if path.suffix == '.jar': jars.add(path)
            elif path.suffix == '.class':
                text = path.as_posix()
                for marker in ('/classes/', '/test-classes/'):
                    if marker in text:
                        member = text.split(marker, 1)[1]
                        if wanted(member): save(text, member, path.read_bytes())
                        break
    for path in sorted(jars):
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if wanted(member): save(path.as_posix(), member, archive.read(member))
    java = Path(shutil.which('java')).resolve()
    javac = Path(shutil.which('javac')).resolve()
    record = {'artifact_type': 'ms94-b06-pinned-class-extraction/1', 'classes': items,
              'java_path': str(java), 'java_sha256': hashlib.sha256(java.read_bytes()).hexdigest(),
              'javac_sha256': hashlib.sha256(javac.read_bytes()).hexdigest(),
              'java_version': subprocess.run([str(java), '-version'], capture_output=True, text=True,
                                             check=True).stderr,
              'jars_scanned': len(jars), 'candidate_executions': 0, 'native_pairs': 0, 'model_calls': 0}
    (out / 'extraction.json').write_text(json.dumps(record, sort_keys=True, indent=2), encoding='utf-8')
    print(json.dumps({'class_entries': len(items), 'distinct_class_bytes': len(list((out / 'class-bytes').iterdir()))}))


if __name__ == '__main__': main()
