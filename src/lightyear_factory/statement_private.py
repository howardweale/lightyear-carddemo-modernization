from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(os.environ.get("LIGHTYEAR_FACTORY_WORKSPACE", "")).resolve()
    path = workspace / "factory/benchmarks/statement_candidate.py"
    if not workspace.is_dir() or workspace not in path.resolve().parents or not path.is_file():
        raise RuntimeError("Statement candidate is unavailable")
    spec = importlib.util.spec_from_file_location("statement_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Statement candidate cannot be loaded")
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    checks = (
        candidate.STATEMENT_JOB == "CREASTMT",
        candidate.STATEMENT_PROGRAM == "CBSTM03A",
        candidate.STATEMENT_RECORD_LENGTH == 80,
        candidate.ACCOUNT_ID_WIDTH == 11,
        candidate.TRANSACTION_ID_WIDTH == 16,
        candidate.HTML_OUTPUT_ENABLED is True,
        candidate.SORT_BEFORE_RENDER is True,
        candidate.statement_key("123", "2026-08") == "00000000123:2026-08",
        candidate.should_render(True, True) is True,
        candidate.should_render(True, False) is False,
    )
    if all(checks):
        print("CREASTMT private policy gate passed")
        return 0
    print("CREASTMT private policy gate failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
