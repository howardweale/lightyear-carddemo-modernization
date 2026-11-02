"""CI-only pinned public binary download; no identity or ciphertext output."""
import hashlib
import io
import os
from pathlib import Path
import tarfile
import urllib.request
import zipfile

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('CI only')
windows = os.name == 'nt'
archive = 'age-v1.3.2-windows-amd64.zip' if windows else 'age-v1.3.2-linux-amd64.tar.gz'
expected = ('f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7' if windows else
            'cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10')
with urllib.request.urlopen('https://github.com/FiloSottile/age/releases/download/v1.3.2/' + archive, timeout=60) as stream:
    raw = stream.read(25 * 1024 * 1024)
if hashlib.sha256(raw).hexdigest() != expected:
    raise SystemExit('archive digest mismatch')
target = Path(os.environ['RUNNER_TEMP']) / 'synthetic-age-pinned'
target.mkdir(mode=0o700)
suffix = '.exe' if windows else ''
names = ['age/age' + suffix, 'age/age-keygen' + suffix]
if windows:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        contents = [z.read(n) for n in names]
else:
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as z:
        contents = [z.extractfile(n).read() for n in names]
paths = []
for name, content in zip(names, contents):
    path = target / Path(name).name
    with path.open('xb') as stream: stream.write(content)
    path.chmod(0o700)
    paths.append(path)
with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
    stream.write('SYNTHETIC_AGE=' + str(paths[0]) + '\n')
    stream.write('SYNTHETIC_AGE_KEYGEN=' + str(paths[1]) + '\n')
    stream.write('SYNTHETIC_AGE_SHA256=' + hashlib.sha256(contents[0]).hexdigest() + '\n')
