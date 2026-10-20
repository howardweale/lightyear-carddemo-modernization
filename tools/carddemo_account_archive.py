"""Verify retained account ZIP members and receipt hash closure; no authority claims."""
from hashlib import sha256
from io import BytesIO
import stat
from types import MappingProxyType
from zipfile import ZipFile
from tools.carddemo_account_evidence import canonical_path, reference

ARCHIVES = frozenset(('carddemo-unsigned-receipt.zip', 'carddemo-proof-mutation.zip',
    'carddemo-proof-browser.zip', 'carddemo-proof-api.zip', 'carddemo-compose-smoke.zip',
    'carddemo-status-render.zip', 'carddemo-web-foundation.zip'))
HASH_GROUPS = frozenset(('generators', 'mappings', 'pinned_sources', 'services', 'sessions', 'ui'))


def _size(value, actual):
    return type(value) is int and value >= 0 and value == actual


def verify_archives(evidence, inventory, bindings):
    """Inputs and ZIP bytes must be bound; return immutable captured member bytes."""
    if (not isinstance(inventory, dict) or inventory.get('schema') != 'carddemo-retained-proof-archives/1'
        or not isinstance(bindings, dict) or set(bindings) != ARCHIVES):
        raise ValueError('account-archive-inventory')
    rows = inventory.get('archives')
    if not isinstance(rows, list) or len(rows) != len(ARCHIVES):
        raise ValueError('account-archive-inventory')
    captured = {}; artifact_ids = set(); names = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'name', 'sha256', 'size', 'original_artifact_id', 'members'}:
            raise ValueError('account-archive-row')
        name = canonical_path(row['name'])
        if name not in ARCHIVES or name in names:
            raise ValueError('account-archive-name')
        names.add(name)
        _, digest = reference(bindings[name])
        artifact = row['original_artifact_id']
        if type(artifact) is not int or artifact <= 0 or artifact in artifact_ids:
            raise ValueError('account-archive-id')
        artifact_ids.add(artifact)
        raw = evidence.read(bindings[name])
        if digest != row['sha256'] or sha256(raw).hexdigest() != digest or not _size(row['size'], len(raw)):
            raise ValueError('account-archive-hash')
        members = row['members']; declared = {}; aliases = set()
        if not isinstance(members, list) or not members:
            raise ValueError('account-archive-members')
        for member in members:
            if not isinstance(member, dict) or set(member) != {'path', 'sha256', 'size'}:
                raise ValueError('account-archive-member')
            path, expected = reference({k:member[k] for k in ('path', 'sha256')})
            if path.casefold() in aliases:
                raise ValueError('account-archive-alias')
            aliases.add(path.casefold()); declared[path] = (expected, member['size'])
        content = {}; all_paths = set()
        with ZipFile(BytesIO(raw)) as archive:
            for item in archive.infolist():
                path = canonical_path(item.filename.rstrip('/') if item.is_dir() else item.filename)
                if path.casefold() in all_paths:
                    raise ValueError('account-archive-alias')
                all_paths.add(path.casefold())
                mode = item.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if item.is_dir():
                    if kind not in (0, stat.S_IFDIR): raise ValueError('account-archive-file-type')
                    continue
                if kind not in (0, stat.S_IFREG) or item.flag_bits & 1:
                    raise ValueError('account-archive-file-type')
                if path not in declared:
                    raise ValueError('account-archive-undeclared-member')
                data = archive.read(item); expected, size = declared[path]
                if sha256(data).hexdigest() != expected or not _size(size, len(data)):
                    raise ValueError('account-archive-member-hash')
                content[path] = data
        if set(content) != set(declared):
            raise ValueError('account-archive-missing-member')
        captured[name[:-4]] = MappingProxyType(content)
    if set(captured) != {name[:-4] for name in ARCHIVES}:
        raise ValueError('account-archive-inventory')
    return MappingProxyType(captured)


def verify_receipt_hashes(receipt, archives, evidence, source_bindings):
    """Verify every receipt hash; Git head/tree provenance remains a separate check."""
    hashes = receipt.get('hashes'); artifact_rows = receipt.get('artifacts')
    if (not isinstance(hashes, dict) or set(hashes) != HASH_GROUPS
        or not isinstance(artifact_rows, list) or not artifact_rows
        or not isinstance(source_bindings, dict)):
        raise ValueError('account-receipt-inventory')
    expected_sources = set(); seen = set(); source_count = 0
    for rows in hashes.values():
        if not isinstance(rows, list) or not rows:
            raise ValueError('account-receipt-inventory')
        for row in rows:
            path, digest = reference(row)
            if path.casefold() in seen: raise ValueError('account-receipt-alias')
            seen.add(path.casefold()); source_count += 1
            if path.startswith('work/'):
                hits = [files[path[5:]] for files in archives.values() if path[5:] in files]
                if not hits or any(sha256(data).hexdigest() != digest for data in hits):
                    raise ValueError('account-receipt-generated-hash')
            else:
                expected_sources.add(path)
                if path not in source_bindings: raise ValueError('account-receipt-source-missing')
                _, bound_digest = reference(source_bindings[path])
                if bound_digest != digest or sha256(evidence.read(source_bindings[path])).hexdigest() != digest:
                    raise ValueError('account-receipt-source-hash')
    if set(source_bindings) != expected_sources:
        raise ValueError('account-receipt-source-inventory')
    seen = set()
    for row in artifact_rows:
        path, digest = reference(row)
        if path.casefold() in seen: raise ValueError('account-receipt-alias')
        seen.add(path.casefold()); prefix = 'work/carddemo-proof-artifacts/'
        if not path.startswith(prefix): raise ValueError('account-receipt-artifact-path')
        parts = path[len(prefix):].split('/', 1)
        if len(parts) != 2 or parts[0] not in archives or parts[1] not in archives[parts[0]]:
            raise ValueError('account-receipt-artifact-missing')
        if sha256(archives[parts[0]][parts[1]]).hexdigest() != digest:
            raise ValueError('account-receipt-artifact-hash')
    return dict(source_and_mapping_hashes=source_count, artifact_hashes=len(artifact_rows))
