from __future__ import annotations

import hashlib
import json
import os
import stat
import shutil
import re
import secrets
from pathlib import Path

from .contracts import ContractError, safe_relative_path


EXCLUDED_NAMES = {
    ".git", ".DS_Store", ".idea", ".vscode", ".venv", "__pycache__", "target", "work"
}


class IsolatedWorkspace:
    """Copy-on-run workspace with strict project-relative write boundaries."""

    def __init__(self, source_root: Path, destination: Path, allowed_paths: tuple[str, ...],
                 read_manifest: dict[str, str] | None = None) -> None:
        self.source_root = source_root.resolve()
        self.root = destination.resolve()
        self.allowed_paths = tuple(safe_relative_path(item) for item in allowed_paths)
        self.read_manifest = dict(read_manifest) if read_manifest is not None else None
        # Controller-private decoys are never part of the mounted worker workspace.
        self.canary_root = self.root.parent / ('.' + self.root.name + '-controller-canaries')
        self.canaries: dict[str, str] = {}
        if self.read_manifest is not None:
            for path,digest in self.read_manifest.items():
                self._strict_relative(path)
                if not re.fullmatch('[0-9a-f]{64}',digest):raise ContractError('workspace-read-hash')
            for path in self.allowed_paths:self._strict_relative(path)

    def create(self) -> None:
        if self.root.exists():
            raise ContractError(f"Factory workspace already exists: {self.root}")
        if self.read_manifest is not None:
            self._create_allowlisted()
            return
        shutil.copytree(
            self.source_root,
            self.root,
            ignore=self._ignore_runtime,
        )

    @staticmethod
    def _strict_relative(path: str) -> str:
        if not isinstance(path,str) or not path or "\\" in path or ":" in path:
            raise ContractError('workspace-read-path')
        if any(part.lower() in ('','.','..','.git') for part in path.split('/')):
            raise ContractError('workspace-read-path')
        return safe_relative_path(path)

    def _create_allowlisted(self) -> None:
        # Validate every byte before creating a destination; never copy a directory.
        if len(self.read_manifest) > 4096:
            raise ContractError('workspace-read-limit')
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                 info.st_mtime_ns, info.st_nlink)
        planned = []; total = 0
        for relative, expected in self.read_manifest.items():
            path = self.source_root/relative
            cursor = path
            while cursor != self.source_root:
                if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                    raise ContractError('workspace-read-symlink')
                cursor = cursor.parent
            if self.source_root not in path.resolve().parents:
                raise ContractError('workspace-read-file')
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ContractError('workspace-read-file')
            total += info.st_size
            if not 0 <= info.st_size <= 8*1024*1024 or total > 32*1024*1024:
                raise ContractError('workspace-read-limit')
            planned.append((relative, path, expected, info))
        # Preflight every size before allocating any file contents or private decoys.
        selected = []
        for relative, path, expected, info in planned:
            with path.open('rb') as handle:
                if identity(os.fstat(handle.fileno())) != identity(info):
                    raise ContractError('workspace-read-replaced')
                data = handle.read(info.st_size+1)
                if identity(os.fstat(handle.fileno())) != identity(info):
                    raise ContractError('workspace-read-replaced')
            cursor = path
            while cursor != self.source_root:
                if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                    raise ContractError('workspace-read-symlink')
                cursor = cursor.parent
            if (len(data) != info.st_size or identity(path.stat()) != identity(info)
                    or self.source_root not in path.resolve().parents):
                raise ContractError('workspace-read-replaced')
            if hashlib.sha256(data).hexdigest() != expected:
                raise ContractError('workspace-read-hash-mismatch')
            selected.append((relative, data))
        if self.canary_root.exists() or self.canary_root.is_symlink():
            raise ContractError('workspace-canary-store-exists')
        self.canary_root.mkdir(mode=0o700, parents=True)
        for kind in ('expected-state', 'reference-output', 'session-answer'):
            token = 'LIGHTYEAR-' + kind + '-' + secrets.token_hex(32)
            with (self.canary_root / (kind + '.txt')).open('x', encoding='utf-8') as handle:
                handle.write(token)
            self.canaries[kind] = token
        self.root.mkdir(parents=True)
        for relative,data in selected:
            target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
        self.verify_read_boundary()

    def full_manifest(self) -> dict[str,str]:
        result={}
        for path in sorted(self.root.rglob('*')):
            relative=path.relative_to(self.root).as_posix()
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or any(p.lower()=='.git' for p in path.parts):raise ContractError('workspace-boundary-symlink-or-history')
            if path.is_file():result[relative]=_file_hash(path)
        return result

    def verify_read_boundary(self) -> dict[str,str]:
        current=self.full_manifest()
        if self.read_manifest is None:return current
        def writable(path):return any(path==p or path.startswith(p.rstrip('/')+'/') for p in self.allowed_paths)
        for path,digest in self.read_manifest.items():
            if not writable(path) and current.get(path)!=digest:raise ContractError('workspace-readonly-changed')
        for path in current:
            if path not in self.read_manifest and not writable(path):raise ContractError('workspace-unlisted-file')
        return current

    def scan_contents(self, scanner, surface):
        """Scan the actual worker-visible files; private history/decoys are outside root."""
        if self.read_manifest is None or not callable(scanner):
            raise ContractError('workspace-isolation-scanner-required')
        try:
            if self.root.is_symlink() or getattr(self.root, 'is_junction', lambda: False)():
                raise ValueError('root')
            scanned = {}; total = 0; entries = 0
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
            for path in self.root.rglob('*'):
                entries += 1
                if entries > 8192:
                    raise ValueError('entry-limit')
                relative = path.relative_to(self.root).as_posix()
                self._strict_relative(relative)
                if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                    raise ValueError('link')
                info = path.stat()
                # Scan names as content, never put private names into the ledger label.
                scanner(surface+'-path', relative.encode('utf-8'))
                if stat.S_ISDIR(info.st_mode):
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8*1024*1024:
                    raise ValueError('file')
                total += info.st_size
                if total > 32*1024*1024 or len(scanned) >= 4096:
                    raise ValueError('byte-limit')
                with path.open('rb') as handle:
                    if identity(os.fstat(handle.fileno())) != identity(info):
                        raise ValueError('replacement')
                    raw = handle.read(8*1024*1024+1)
                    if identity(os.fstat(handle.fileno())) != identity(info):
                        raise ValueError('replacement')
                if (len(raw) != info.st_size or path.is_symlink()
                        or getattr(path, 'is_junction', lambda: False)()
                        or identity(path.stat()) != identity(info)):
                    raise ValueError('replacement')
                scanner(surface+'-file', raw)
                scanned[relative] = hashlib.sha256(raw).hexdigest()
            if self.verify_read_boundary() != scanned:
                raise ValueError('manifest-drift')
            return {'files': len(scanned), 'bytes': total,
                    'manifest_sha256': hashlib.sha256(json.dumps(scanned, sort_keys=True).encode()).hexdigest()}
        except Exception:
            raise ContractError('workspace-isolation-refused') from None

    def _ignore_runtime(self, directory, names):
        ignored = set(shutil.ignore_patterns(*EXCLUDED_NAMES, "*.pyc")(directory, names))
        relative = Path(directory).relative_to(self.source_root).as_posix()
        if relative == "factory/idempiere/ms86-journeys" and "runs" in names:
            ignored.add("runs")
        return ignored

    def resolve(self, relative_path: str, require_allowed: bool = True) -> Path:
        normalized = safe_relative_path(relative_path)
        if self.read_manifest is not None:self._strict_relative(normalized)
        candidate = (self.root / normalized).resolve()
        if self.root not in candidate.parents:
            raise ContractError(f"Path escapes factory workspace: {relative_path}")
        if require_allowed and not any(
            normalized == allowed or normalized.startswith(allowed.rstrip("/") + "/")
            for allowed in self.allowed_paths
        ):
            raise ContractError(f"Builder may not modify {relative_path}")
        return candidate

    def snapshot(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for allowed in self.allowed_paths:
            path = self.resolve(allowed)
            if path.is_file():
                hashes[allowed] = _file_hash(path)
            elif path.is_dir():
                for item in sorted(path.rglob("*")):
                    if item.is_file():
                        hashes[item.relative_to(self.root).as_posix()] = _file_hash(item)
        return hashes


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

