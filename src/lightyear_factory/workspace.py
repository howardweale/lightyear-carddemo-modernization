from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .contracts import ContractError, safe_relative_path


EXCLUDED_NAMES = {
    ".git", ".DS_Store", ".idea", ".vscode", ".venv", "__pycache__", "target", "work"
}


class IsolatedWorkspace:
    """Copy-on-run workspace with strict project-relative write boundaries."""

    def __init__(self, source_root: Path, destination: Path, allowed_paths: tuple[str, ...]) -> None:
        self.source_root = source_root.resolve()
        self.root = destination.resolve()
        self.allowed_paths = tuple(safe_relative_path(item) for item in allowed_paths)

    def create(self) -> None:
        if self.root.exists():
            raise ContractError(f"Factory workspace already exists: {self.root}")
        shutil.copytree(
            self.source_root,
            self.root,
            ignore=self._ignore_runtime,
        )

    def _ignore_runtime(self, directory, names):
        ignored = set(shutil.ignore_patterns(*EXCLUDED_NAMES, "*.pyc")(directory, names))
        relative = Path(directory).relative_to(self.source_root).as_posix()
        if relative == "factory/idempiere/ms86-journeys" and "runs" in names:
            ignored.add("runs")
        return ignored

    def resolve(self, relative_path: str, require_allowed: bool = True) -> Path:
        normalized = safe_relative_path(relative_path)
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

