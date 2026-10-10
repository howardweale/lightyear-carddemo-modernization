"""Read cache whose lifetime is one explicit verification pass, never global."""
from collections import Counter
import io
import zipfile

class VerificationReadCache:
    def __init__(self):
        self._bytes = {}
        self._archives = {}
        self._closed = False

    def __enter__(self):
        if self._closed:
            raise ValueError("verification-pass-closed")
        return self

    def read(self, key, loader):
        if self._closed:
            raise ValueError("verification-pass-closed")
        if key not in self._bytes:
            self._bytes[key] = loader()
        return self._bytes[key]

    def member(self, key, loader, members, *, ambiguity_error="archive-member-ambiguous"):
        body = self.read(key, loader)
        chain = key
        for member in members:
            if chain not in self._archives:
                jar = zipfile.ZipFile(io.BytesIO(body))
                self._archives[chain] = jar, Counter(jar.namelist())
            jar, counts = self._archives[chain]
            if counts[member] != 1:
                raise ValueError(ambiguity_error)
            body = jar.read(member)
            chain = (*chain, member)
        return body

    def __exit__(self, *_):
        for jar, _counts in self._archives.values():
            jar.close()
        self._archives.clear()
        self._bytes.clear()
        self._closed = True
