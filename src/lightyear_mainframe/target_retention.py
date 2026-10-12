"""Hash-only case receipts with selectively retained deterministic gzip CAS blobs."""
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import time
from .campaign_provenance import sealed
from .legacy_twin import write_json

BUDGET = 8 * 1024**3


def size(folder):
    return sum(p.stat().st_size for p in Path(folder).rglob('*') if p.is_file())


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class Retention:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir()  # never resume, even on the same head
        self.cas = self.root / 'cas'
        self.cas.mkdir()
        self.runs = 0
        self.logical_bytes = 0
        self.peak_temporary_bytes = 0
        self.execution_seconds = 0.0
        self.peak_stored_bytes = 0
        self.cached_stored_bytes = 0
        self.active_bytes = 0
        self.started = time.monotonic()

    @contextmanager
    def case(self, target, name, attempt):
        # TemporaryDirectory owns and removes only this fresh case's folder.
        with tempfile.TemporaryDirectory(prefix='case-', dir=self.root) as temporary:
            folder = Path(temporary) / 'run'
            start = time.monotonic()
            result = attempt(target, name, folder)
            elapsed = time.monotonic() - start
            files = {}
            for path in sorted(folder.rglob('*')):
                if path.is_symlink():
                    raise ValueError('case-symlink-refused')
                if path.is_file():
                    files[path.relative_to(folder).as_posix()] = dict(sha256=file_hash(path), bytes=path.stat().st_size)
            rc = result.get('returncode')
            program = folder / 'logs/program.json'
            if program.exists():
                rc = json.loads(program.read_text()).get('returncode', rc)
            item = dict(result, returncode=rc, files=files, execution_seconds=elapsed,
                        retained=False, retention_reasons=[])
            item['exact_stdout_sha256']=files.get('logs/program.stdout',{}).get('sha256')
            item['exact_stderr_sha256']=files.get('logs/program.stderr',{}).get('sha256')
            item['output_file_sha256s']={k:v['sha256'] for k,v in files.items() if k.startswith(('after/','files/'))}
            self.runs += 1
            serial=self.runs
            item['logical_bytes']=sum(f['bytes'] for f in files.values())
            raw_bytes = sum(f['bytes'] for f in files.values())
            self.logical_bytes += raw_bytes
            self.execution_seconds += elapsed
            self.active_bytes += raw_bytes
            self.peak_temporary_bytes = max(self.peak_temporary_bytes,self.active_bytes)
            self.peak_stored_bytes=max(self.peak_stored_bytes,self.cached_stored_bytes+self.active_bytes)
            if self.cached_stored_bytes+self.active_bytes > BUDGET:
                # Preserve refusal/partial bytes before refusing further cases.
                self.retain(folder, item, ['output-budget-refusal'])
                write_json(self.root/f'run-{serial:07d}.json',item)
                raise RuntimeError('B1-targeted-output-budget-exhausted')
            try:
                yield folder, item
            finally:
                if result['status'] != 'executed' and not item['retained']:
                    self.retain(folder, item, ['execution-refusal'])
                path=self.root/f'run-{serial:07d}.json'
                write_json(path,item)
                self.cached_stored_bytes+=path.stat().st_size
                self.active_bytes-=raw_bytes

    def retain(self, folder, item, reasons):
        item['retained'] = True
        item['retention_reasons'] = sorted(set(item['retention_reasons'] + reasons))
        for name, record in item['files'].items():
            blob = self.cas / (record['sha256'] + '.gz')
            if not blob.exists():
                with (folder/name).open('rb') as source, blob.open('xb') as output:
                    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0, compresslevel=1) as zipped:
                        for block in iter(lambda: source.read(1024*1024), b''):
                            zipped.write(block)
                self.cached_stored_bytes+=blob.stat().st_size
            record['blob'] = 'cas/' + blob.name
            self.peak_stored_bytes=max(self.peak_stored_bytes,self.cached_stored_bytes+self.active_bytes)

    def metrics(self):
        return dict(runs=self.runs, logical_run_bytes=self.logical_bytes,
                    bytes_per_run=self.logical_bytes/self.runs if self.runs else 0,
                    retained_compressed_bytes=size(self.cas), stored_bytes=size(self.root),
                    peak_temporary_bytes=self.peak_temporary_bytes,peak_stored_bytes=self.peak_stored_bytes,
                    execution_seconds=self.execution_seconds, wall_seconds=time.monotonic()-self.started,
                    budget_bytes=BUDGET)

    def seal(self, head):
        records = {p.relative_to(self.root).as_posix(): file_hash(p)
                   for p in sorted(self.root.rglob('*')) if p.is_file()}
        value = sealed(dict(schema='target-retention/1', head=head, metrics=self.metrics(), files=records))
        write_json(self.root/'manifest.json', value)
        return value


def verify_retention(root, head):
    from .campaign_provenance import read_sealed
    root = Path(root).resolve()
    manifest = read_sealed(root/'manifest.json')
    if manifest['head'] != head:
        raise ValueError('retention-head-mismatch')
    actual = {p.relative_to(root).as_posix(): file_hash(p) for p in root.rglob('*')
              if p.is_file() and p != root/'manifest.json'}
    if actual != manifest['files']:
        raise ValueError('retention-inventory-mismatch')
    for blob in (root/'cas').glob('*.gz'):
        h = hashlib.sha256()
        with gzip.open(blob, 'rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''):
                h.update(block)
        if h.hexdigest() != blob.stem:
            raise ValueError('retention-blob-digest-mismatch')
    return manifest


def paired_case(retention, base, changed, name, index, witnessed, attempt, classify):
    with retention.case(base,name,attempt) as (basefolder,normal):
        with retention.case(changed,name,attempt) as (folder,actual):
            status=classify(normal,actual)
            reasons=[]
            if index in (0,199):reasons.append('fixed-sample')
            if status.startswith('killed-') and not witnessed:reasons.append('first-killing-witness')
            if normal['status']!='executed' or actual['status']!='executed':reasons.append('execution-refusal')
            if reasons:
                retention.retain(basefolder,normal,reasons)
                retention.retain(folder,actual,reasons)
            return dict(index=index,case=name,baseline=normal,actual=actual,status=status)
