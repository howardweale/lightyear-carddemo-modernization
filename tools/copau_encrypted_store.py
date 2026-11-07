"""Synthetic-CI encrypt-on-write integration for the held-out helper.

No production entry point. Software identities are disposable CI fixtures only.
The unchanged helper consumes the Store interface; private bytes enter age via
stdin and only authenticated ciphertext reaches the underlying private store.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess

from tools.copau_private_prerequisites import Refused, require, LIMIT, no_links


class EncryptedStore:
    def __init__(self, private_store, age, age_sha256, recipients, identity):
        require(os.environ.get('GITHUB_ACTIONS') == 'true')
        require(len(recipients) == 2 and len(set(recipients)) == 2)
        # Native software recipients only in this qualification tranche.
        require(all(re.fullmatch(r'age1[023456789acdefghjklmnpqrstuvwxyz]{58}', r)
                    for r in recipients))
        self.inner = private_store
        self.root = private_store.root
        self.age = Path(age).absolute()
        self.identity = Path(identity).absolute()
        self.age_sha256 = age_sha256
        self.recipients = tuple(recipients)
        self._tool()

    def _tool(self):
        no_links(self.age)
        require(self.age.is_file() and re.fullmatch('[0-9a-f]{64}', self.age_sha256))
        require(hashlib.sha256(self.age.read_bytes()).hexdigest() == self.age_sha256)

    def _name(self, name):
        require(re.fullmatch('[a-z][a-z0-9-]*[.]json', name))
        return name[:-5] + '-age.json'

    def path(self, name):
        return self.inner.path(self._name(name))

    def initialize(self):
        self.inner.initialize()

    def check(self):
        self.inner.check()

    def absent(self, *names):
        self.inner.absent(*(self._name(n) for n in names))

    def _age(self, args, raw):
        self._tool()
        require(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT)
        # No agent/provider credentials, shell expansion or inherited output.
        env = {k: os.environ[k] for k in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')
               if k in os.environ}
        env['PATH'] = str(self.age.parent)
        try:
            result = subprocess.run([str(self.age), *args], input=raw,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                timeout=30, check=False)
            require(result.returncode == 0 and 0 < len(result.stdout) <= LIMIT)
            return result.stdout
        except (OSError, subprocess.TimeoutExpired):
            raise Refused() from None

    def write(self, name, raw):
        self.absent(name)
        require(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT - 4096)
        args = ['--encrypt']
        for recipient in self.recipients:
            args += ['--recipient', recipient]
        ciphertext = self._age(args, raw)
        require(ciphertext.startswith(b'age-encryption.org/v1\n'))
        # Authentication and byte equality are checked in memory before commit.
        require(self._decrypt(ciphertext) == raw)
        self.inner.write(self._name(name), ciphertext)
        require(self.read(name) == raw)

    def _decrypt(self, ciphertext):
        no_links(self.identity)
        require(self.identity.is_file() and self.identity.stat().st_size <= 4096)
        # run() returns output only after success; partial unauthenticated output
        # from a failed age process is discarded, never sent to the helper.
        return self._age(['--decrypt', '--identity', str(self.identity)], ciphertext)

    def read(self, name):
        return self._decrypt(self.inner.read(self._name(name)))


def prepare_encrypted(store, root, seed, index, *, seed_commitment=False):
    """Use the original generation/selection/scanning code with an encrypted sink."""
    from tools import copau_answer_key
    require(type(store) is EncryptedStore)
    return copau_answer_key.prepare(store, root, seed, index, True, seed_commitment)
