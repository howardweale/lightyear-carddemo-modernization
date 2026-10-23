"""Real pinned-tool synthetic probes, invoked only by the future P1 CI job.

Not part of ordinary unittest discovery: tools must first be provisioned in CI.
No vulnerable dependency, secret value or scanner diagnostic is printed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from tools.ci.p1_capture import CaptureRefused, capture
from tools.ci.p1_quality_collect import decode_json_lines


def quality_probes():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise CaptureRefused("ci-only")
    with tempfile.TemporaryDirectory(prefix="p1-quality-probes-") as temp:
        root = Path(temp)
        (root / "unused.py").write_text("import os\n", encoding="utf-8")
        code, out, _ = capture([sys.executable, "-m", "ruff", "check", "--isolated", "--output-format=json", "unused.py"], root)
        rows = json.loads(out)
        if code != 1 or not any(r["code"] == "F401" for r in rows):
            raise CaptureRefused("ruff-negative-control")
        (root / "formatting.py").write_text("x=  1\n", encoding="utf-8")
        code, _, _ = capture([sys.executable, "-m", "ruff", "format", "--isolated", "--check", "formatting.py"], root)
        if code != 1:
            raise CaptureRefused("format-negative-control")
        (root / "mismatch.py").write_text('value: int = "synthetic"\n', encoding="utf-8")
        code, out, _ = capture([sys.executable, "-m", "mypy", "--config-file=", "--no-incremental", "--no-error-summary", "--output=json", "mismatch.py"], root)
        rows = decode_json_lines(out)
        if code != 1 or not any(r["code"] == "assignment" and r["severity"] == "error" for r in rows):
            raise CaptureRefused("mypy-negative-control")
        (root / "clean.py").write_text("value: int = 1\n", encoding="utf-8")
        for command in (
            [sys.executable, "-m", "ruff", "check", "--isolated", "clean.py"],
            [sys.executable, "-m", "ruff", "format", "--isolated", "--check", "clean.py"],
            [sys.executable, "-m", "mypy", "--config-file=", "--no-incremental", "clean.py"],
        ):
            code, _, _ = capture(command, root)
            if code:
                raise CaptureRefused("quality-positive-control")
    return dict(ruff=True, ruff_format=True, mypy=True)


def main():
    try:
        print(json.dumps(dict(quality_probes=quality_probes(), security_probes="not implemented")))
        return 0
    except Exception:
        print("P1 quality acceptance probe failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
