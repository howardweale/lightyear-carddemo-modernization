"""Offline Git object verification for captured account evidence; no Git process or network."""
from hashlib import sha1, sha256
import re
from tools.carddemo_account_evidence import canonical_path


def verify_git_sources(objects, evidence, source, tested, base, bindings):
    if not isinstance(objects, dict) or not isinstance(bindings, dict):
        raise ValueError('account-git-inputs')
    if any(not isinstance(oid, str) or not re.fullmatch('[0-9a-f]{40}', oid)
           for oid in [source, tested, base, *objects]):
        raise ValueError('account-git-oid')
    used = set()
    def object_bytes(oid, kind):
        if oid not in objects: raise ValueError('account-git-missing-object')
        raw = evidence.read(objects[oid]); used.add(oid)
        if sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != oid:
            raise ValueError('account-git-object-hash')
        return raw
    def commit(oid):
        lines = object_bytes(oid, 'commit').split(b'\n\n', 1)[0].splitlines()
        trees = [line[5:].decode('ascii') for line in lines if line.startswith(b'tree ')]
        parents = [line[7:].decode('ascii') for line in lines if line.startswith(b'parent ')]
        if len(trees) != 1 or any(not re.fullmatch('[0-9a-f]{40}', v) for v in trees + parents):
            raise ValueError('account-git-commit')
        return trees[0], parents
    tree, _ = commit(source); test_tree, parents = commit(tested)
    if tree != test_tree or parents != [base, source]:
        raise ValueError('account-git-tested-tree-parents')
    cache = {}
    def entries(oid):
        if oid in cache: return cache[oid]
        raw = object_bytes(oid, 'tree'); result = {}; offset = 0
        while offset < len(raw):
            end = raw.index(b'\0', offset); mode, name = raw[offset:end].split(b' ', 1)
            name = name.decode('utf-8'); canonical_path(name)
            if '/' in name or name.casefold() in {key.casefold() for key in result} or end + 21 > len(raw):
                raise ValueError('account-git-tree-entry')
            result[name] = (mode.decode('ascii'), raw[end+1:end+21].hex()); offset = end + 21
        cache[oid] = result
        return result
    result = {}; seen = set()
    for path, ref in bindings.items():
        canonical_path(path)
        if path.casefold() in seen: raise ValueError('account-git-source-alias')
        seen.add(path.casefold()); oid = tree; parts = path.split('/')
        for part in parts[:-1]:
            mode, oid = entries(oid)[part]
            if mode != '40000': raise ValueError('account-git-directory')
        mode, oid = entries(oid)[parts[-1]]
        if mode not in ('100644', '100755'): raise ValueError('account-git-source-mode')
        raw = evidence.read(ref)
        if sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != oid:
            raise ValueError('account-git-source-blob')
        result[path] = {'blob': oid, 'mode': mode, 'sha256': sha256(raw).hexdigest()}
    if used != set(objects): raise ValueError('account-git-object-closure')
    return {'tree': tree, 'tested_parents': parents, 'sources': result,
            'binding': 'captured Git object content identities; no signature or authority claim'}
