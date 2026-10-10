"""Digest-verified, bounded reads scoped to one explicit verification pass."""
from collections import Counter
import hashlib
import io
import re
import zipfile


class VerificationReadCache:
    def __init__(self, *, max_archive_bytes=1024**3, max_member_bytes=256*1024**2,
                 max_entries=100000, max_total_bytes=1024**3, max_depth=8):
        for limit in (max_archive_bytes, max_member_bytes, max_entries, max_total_bytes, max_depth):
            if type(limit) is not int or limit <= 0:
                raise ValueError('verification-limit-invalid')
        self.max_archive_bytes = max_archive_bytes
        self.max_member_bytes = max_member_bytes
        self.max_entries = max_entries
        self.max_total_bytes = max_total_bytes
        self.max_depth = max_depth
        self._bytes = {}
        self._archives = {}
        self._closed = False

    def __enter__(self):
        if self._closed:
            raise ValueError('verification-pass-closed')
        return self

    def read(self, key, loader):
        if self._closed:
            raise ValueError('verification-pass-closed')
        if not isinstance(key, tuple) or len(key) != 2 or not isinstance(key[1], str) or not re.fullmatch('[0-9a-f]{64}', key[1]):
            raise ValueError('verification-digest-key-required')
        if key not in self._bytes:
            body = loader()
            if not isinstance(body, bytes):
                raise ValueError('verification-bytes-required')
            if len(body) > self.max_archive_bytes:
                raise ValueError('verification-archive-bound')
            if hashlib.sha256(body).hexdigest() != key[1]:
                raise ValueError('verification-content-digest-mismatch')
            # Failed loads are never cached. Keys contain the expected digest.
            self._bytes[key] = body
        return self._bytes[key]

    def member(self, key, loader, members, *, ambiguity_error='archive-member-ambiguous'):
        if len(members) > self.max_depth:
            raise ValueError('verification-depth-bound')
        body = self.read(key, loader)
        chain = key
        for member in members:
            if chain not in self._archives:
                if len(body) > self.max_archive_bytes:
                    raise ValueError('verification-archive-bound')
                jar = zipfile.ZipFile(io.BytesIO(body))
                try:
                    infos = jar.infolist()
                    if len(infos) > self.max_entries:
                        raise ValueError('verification-entry-bound')
                    if sum(info.file_size for info in infos) > self.max_total_bytes:
                        raise ValueError('verification-total-bound')
                    counts = Counter(info.filename for info in infos)
                except BaseException:
                    jar.close()
                    raise
                self._archives[chain] = jar, counts
            jar, counts = self._archives[chain]
            if counts[member] != 1:
                raise ValueError(ambiguity_error)
            info = jar.getinfo(member)
            if info.file_size > self.max_member_bytes:
                raise ValueError('verification-member-bound')
            # Bound decompression before allocating a nested archive/member.
            with jar.open(info) as stream:
                body = stream.read(self.max_member_bytes + 1)
            if len(body) > self.max_member_bytes:
                raise ValueError('verification-member-bound')
            chain = (*chain, member)
        return body

    def __exit__(self, *_):
        for jar, _counts in self._archives.values():
            jar.close()
        self._archives.clear()
        self._bytes.clear()
        self._closed = True
