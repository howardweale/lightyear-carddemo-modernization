from __future__ import annotations

import hashlib
import shutil
import re
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
        selected=[]
        for relative,expected in self.read_manifest.items():
            path=self.source_root/relative
            cursor=path
            while cursor!=self.source_root:
                if cursor.is_symlink() or getattr(cursor,'is_junction',lambda:False)():raise ContractError('workspace-read-symlink')
                cursor=cursor.parent
            if not path.is_file() or self.source_root not in path.resolve().parents:
                raise ContractError('workspace-read-file')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected:raise ContractError('workspace-read-hash-mismatch')
            selected.append((relative,data))
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

