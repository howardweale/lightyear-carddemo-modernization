from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import ContractError, WorkOrder, canonical_hash
from .workspace import IsolatedWorkspace


class PatchBroker:
    """Validate a model proposal completely before applying bounded text edits."""

    def apply(
        self,
        order: WorkOrder,
        workspace: IsolatedWorkspace,
        edits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not isinstance(edits, list):
            raise ContractError("Builder edits must be an array")
        paths = {str(item.get("path", "")) for item in edits}
        if len(paths) > order.max_files_changed:
            raise ContractError("Builder exceeded max_files_changed")
        total_patch_bytes = 0
        originals: dict[str, str] = {}
        proposed: dict[str, str] = {}
        rationales: dict[str, list[str]] = {}

        for edit in edits:
            relative = str(edit.get("path", ""))
            find = edit.get("find")
            replace = edit.get("replace")
            if not isinstance(find, str) or not find or not isinstance(replace, str):
                raise ContractError("Every edit requires non-empty find text and replacement text")
            direct_path = workspace.root / relative
            if direct_path.is_symlink():
                raise ContractError(f"Builder may not modify a symlink: {relative}")
            path = workspace.resolve(relative)
            if not path.is_file():
                raise ContractError(f"Builder target is not a file: {relative}")
            if relative not in originals:
                raw = path.read_bytes()
                if b"\0" in raw:
                    raise ContractError(f"Builder target is not a text file: {relative}")
                if len(raw) > order.max_file_bytes:
                    raise ContractError(f"Builder target exceeds max_file_bytes: {relative}")
                originals[relative] = raw.decode("utf-8")
                proposed[relative] = originals[relative]
                rationales[relative] = []
            occurrences = proposed[relative].count(find)
            if occurrences != 1:
                raise ContractError(
                    f"Edit for {relative} expected one exact match; found {occurrences}"
                )
            total_patch_bytes += len(find.encode("utf-8")) + len(replace.encode("utf-8"))
            if total_patch_bytes > order.max_patch_bytes:
                raise ContractError("Builder exceeded max_patch_bytes")
            proposed[relative] = proposed[relative].replace(find, replace, 1)
            rationales[relative].append(str(edit.get("rationale", ""))[:1_000])

        changes = []
        total_changed_lines = 0
        for relative in sorted(proposed):
            before = originals[relative]
            after = proposed[relative]
            if before == after:
                raise ContractError(f"Builder edit made no change: {relative}")
            diff_lines = list(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                    n=3,
                )
            )
            changed_lines = sum(
                1
                for line in diff_lines
                if (line.startswith("+") or line.startswith("-"))
                and not line.startswith("+++")
                and not line.startswith("---")
            )
            total_changed_lines += changed_lines
            if total_changed_lines > order.max_changed_lines:
                raise ContractError("Builder exceeded max_changed_lines")
            diff_text = "".join(diff_lines)
            changes.append(
                {
                    "path": relative,
                    "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                    "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
                    "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
                    "changed_lines": changed_lines,
                    "rationales": rationales[relative],
                }
            )

        # All policy checks have completed. Replace each file without exposing a partially written file.
        for relative in sorted(proposed):
            path = workspace.resolve(relative)
            mode = path.stat().st_mode
            descriptor, temporary = tempfile.mkstemp(prefix=".lightyear-patch-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                    handle.write(proposed[relative])
                os.chmod(temporary, mode)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

        result = {
            "broker": "lightyear-constrained-patch-broker",
            "changes": changes,
            "files_changed": len(changes),
            "patch_bytes": total_patch_bytes,
            "changed_lines": total_changed_lines,
        }
        result["content_sha256"] = canonical_hash(result)
        return result

