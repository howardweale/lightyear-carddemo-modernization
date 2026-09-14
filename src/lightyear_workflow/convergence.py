"""Convergence projection for the Control Tower.

Wires into `explorer.py` beside the existing workflow handlers:

    if path == "/api/workflow/convergence":
        self._json(read_convergence(self.server.project_root,
                                    estate=self._value(query, "estate"),
                                    weeks=int(self._value(query, "weeks") or 12)))
        return

Read-only by construction. It opens the run index and nothing else — no journal
is read, so the view keeps working after retention has pruned them, which is the
property the whole split exists for.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from lightyear_workflow.run_index import RunIndex

INDEX_RELATIVE = Path("control-tower") / "run-index.sqlite3"
DEFAULT_ESTATE = "cloudbank"
MAX_WEEKS = 52


def read_convergence(project_root: Path, *, estate: str | None = None,
                     weeks: int = 12) -> dict:
    """The weekly trend and what it is costing to keep.

    An absent index is not an error. It means no run has finished yet, and the
    view says so rather than rendering zeroes that look like a result.
    """
    index_path = Path(project_root) / INDEX_RELATIVE
    if not index_path.exists():
        return {"weeks": [], "storage": None,
                "reason": "no-runs-recorded"}

    try:
        return _read(index_path, estate or DEFAULT_ESTATE, weeks)
    except (OSError, ValueError, sqlite3.Error):
        return {"weeks": [], "storage": None, "reason": "invalid-run-index"}


def _read(index_path: Path, estate: str, weeks: int) -> dict:
    index = RunIndex(index_path, read_only=True)
    bounded = max(1, min(int(weeks or 12), MAX_WEEKS))
    return {
        "estate": estate or DEFAULT_ESTATE,
        "metric_unit": "action-events",
        "storage_scope": "all-estates",
        "weeks": index.convergence(estate or DEFAULT_ESTATE, weeks=bounded),
        "storage": index.storage(),
        "retention_note": (
            "Journals are pruned on the customer's retention policy. Index rows "
            "and content hashes are kept, so a pruned run remains a recorded gap."
        ),
    }
