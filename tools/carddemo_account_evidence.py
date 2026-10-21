"""Hash-bound account publication inputs; no proof or execution authority."""
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import stat
from types import MappingProxyType


def _json_value(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('account-evidence-duplicate-key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('account-evidence-nonfinite')

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('account-evidence-nonfinite')
        return result

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float)


def json_document(raw):
    value = _json_value(raw)
    if not isinstance(value, dict):
        raise ValueError('account-evidence-object')
    return value


def json_rows(raw):
    value = _json_value(raw)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError('account-evidence-rows')
    return value


def canonical_path(value):
    if not isinstance(value, str) or not value or any(c in value for c in ('\\', ':', '\x00', '\r', '\n')):
        raise ValueError('account-evidence-path')
    if any(ord(c) < 32 or c in '<>"|?*' for c in value):
        raise ValueError('account-evidence-path')
    parts = value.split('/')
    for part in parts:
        if (not part or part in ('.', '..') or part.endswith((' ', '.'))
            or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part)):
            raise ValueError('account-evidence-path')
    return value


def reference(value):
    if (not isinstance(value, dict) or set(value) != {'path', 'sha256'}
        or not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('account-evidence-reference')
    return canonical_path(value['path']), value['sha256']


def _read(root, path):
    current = root
    parts = path.split('/')
    try:
        for index, part in enumerate(parts):
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('account-evidence-link')
            expected = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
            if not expected(info.st_mode):
                raise ValueError('account-evidence-file-type')
        current.resolve(strict=True).relative_to(root)
        return current.read_bytes()
    except OSError as error:
        raise ValueError('account-evidence-unreadable') from error


class BoundEvidence:
    """Capture every manifest member once; semantic proof validation is separate."""
    def __init__(self, root, manifest_reference):
        root = Path(root).resolve(strict=True)
        manifest_path, digest = reference(manifest_reference)
        raw = _read(root, manifest_path)
        if sha256(raw).hexdigest() != digest:
            raise ValueError('account-evidence-manifest-hash')
        manifest = json_document(raw)
        if not manifest:
            raise ValueError('account-evidence-empty-manifest')
        paths = {manifest_path.casefold()}; captured = {}; digests = {}
        for path, expected in manifest.items():
            path, expected = reference(dict(path=path, sha256=expected))
            if path.casefold() in paths:
                raise ValueError('account-evidence-path-alias')
            paths.add(path.casefold())
            data = _read(root, path)
            if sha256(data).hexdigest() != expected:
                raise ValueError('account-evidence-member-hash')
            captured[path] = data; digests[path] = expected
        self._raw = MappingProxyType(captured)
        self._digests = MappingProxyType(digests)
        self.inputs = (manifest_path, *sorted(captured))

    def read(self, bound_reference):
        path, digest = reference(bound_reference)
        if self._digests.get(path) != digest:
            raise ValueError('account-evidence-unbound-reference')
        return self._raw[path]

    def document(self, bound_reference):
        return json_document(self.read(bound_reference))
