"""Operator-only seed custody; #430 ACL verifier remains unchanged."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import logging
import os
from pathlib import Path
import secrets
import stat
import sys
from tools import copau_private_prerequisites as custody

SEED = 'heldout-seed.json'
DEFAULT = custody.ROOT / 'copau-key-1'
FILE_ACL = r"""
$ErrorActionPreference='Stop'
$path=[Console]::In.ReadToEnd() | ConvertFrom-Json
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true,$false)
$acl.SetOwner($sid)
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','Allow'))
[IO.File]::SetAccessControl($path,$acl)
"""

class PrivateStore:
    def __init__(self, root, exposed, expected_sid=None):
        self.root = Path(root).expanduser().absolute()
        custody.require(not any(p.casefold() == '.codex' or p.casefold().startswith('onedrive')
                                for p in self.root.parts))
        for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
            if os.environ.get(name):
                other = Path(os.environ[name]).absolute()
                custody.require(self.root != other and other not in self.root.parents)
        self.inner = custody.Store(self.root, exposed)
        self.expected_sid = expected_sid

    def check(self):
        self.inner.check()
        self.strict(self.root, directory=True)

    def strict(self, path, directory=False):
        custody.no_links(path)
        if os.name == 'nt':
            sid, rows = custody.windows_acl([path])
            custody.require(sid == self.expected_sid)
            custody.private_acl(rows[0], sid, directory)
            custody.require(rows[0]['owner'] == sid and rows[0]['protected'])
            custody.require(all(r['allow'] and r['sid'] == sid for r in rows[0]['rules']))
        else:
            info = path.stat()
            custody.require(info.st_uid == os.getuid() and
                            stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600))

    def initialize(self):
        if os.name == 'nt':
            sid, _ = custody.windows_acl([self.root.parent])
            custody.require(sid == self.expected_sid)
        self.inner.initialize(); self.check()

    def path(self, name):return self.inner.path(name)
    def absent(self, *names):self.check(); self.inner.absent(*names)

    def read(self, name):
        self.check(); self.strict(self.path(name))
        raw = self.inner.read(name)
        self.strict(self.path(name)); return raw

    def write(self, name, raw):
        self.check()
        # O_EXCL and the already Howard-only parent protect the initial write.
        # Then make the file DACL explicit and verify the effective allow set.
        self.inner.write(name, raw)
        if os.name == 'nt':custody.powershell(FILE_ACL, str(self.path(name)))
        self.strict(self.path(name))
        custody.require(self.read(name) == raw)

def seed_for(store, index_sha256, *, reuse=False):
    if not os.path.lexists(store.root):
        custody.require(not reuse); store.initialize()
    store.check()
    if os.path.lexists(store.path(SEED)):
        record = custody.load_json(store.read(SEED))
        custody.require(set(record) == {'schema','seed_hex','created_at','index_sha256'} and
                        record['schema'] == 'copau-os-seed/1' and
                        record['index_sha256'] == index_sha256)
        seed = bytes.fromhex(record['seed_hex'])
        custody.require(len(seed) == 32 and len(record['seed_hex']) == 64)
        datetime.fromisoformat(record['created_at'])
        return seed, record, False
    custody.require(not reuse and not any(store.root.iterdir()))
    seed = secrets.token_bytes(32)
    custody.require(isinstance(seed, bytes) and len(seed) == 32)
    record = dict(schema='copau-os-seed/1', seed_hex=seed.hex(),
                  created_at=datetime.now(timezone.utc).isoformat(), index_sha256=index_sha256)
    store.write(SEED, custody.encoded(record))
    return seed, record, True

@contextmanager
def quiet_private():
    """Suppress Python streams, logging and inherited stdout/stderr file descriptors."""
    previous = logging.root.manager.disable
    saved = []
    with open(os.devnull, 'w') as sink:
        try:
            for fd in (1, 2):
                duplicate = os.dup(fd); saved.append((fd, duplicate)); os.dup2(sink.fileno(), fd)
            logging.disable(sys.maxsize)
            with redirect_stdout(sink), redirect_stderr(sink):yield
        finally:
            logging.disable(previous)
            for fd, duplicate in reversed(saved):os.dup2(duplicate, fd); os.close(duplicate)

def replay(store, root, seed, run_session, bundle_info):
    """Regenerate in memory, byte-compare; never rewrite original private evidence."""
    values, provenance = run_session(root, seed)
    raw = custody.encoded(dict(schema='factory-private-expected-values/1', values=values))
    original = custody.load_json(store.read('heldout-provenance.json'))
    custody.require(original['producer'] == provenance['producer'] and
                    original['output_sha256'] == provenance['output_sha256'] and
                    raw == store.read('copau-expected-values.json'))
    return bundle_info(raw)
