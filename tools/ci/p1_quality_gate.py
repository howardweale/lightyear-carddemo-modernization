"""Compare a measured quality report with the trusted-base baseline."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from tools.ci.p1_capture import capture
from tools.ci.p1_reports import baseline_gate, ReportRefused
from tools.ci.p1_quality_collect import collect


BASELINE = "docs/platform/p1-quality-baseline.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--measurement", type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"[0-9a-f]{40}", args.base):
            raise ReportRefused("ci-only")
        observed = json.loads(args.measurement.read_bytes())
        code, raw, _ = capture(["git", "show", args.base + ":" + BASELINE], Path.cwd())
        if code:
            if not Path(BASELINE).is_file():
                print("P1 initial baseline review required; measurement retained")
                return 1
            # Bootstrap against an independently scanned trusted base, never
            # against the candidate's own findings. Subsequent baselines use
            # the committed trusted-base file and can only shrink.
            with tempfile.TemporaryDirectory(prefix="p1-base-") as temp:
                checkout = Path(temp) / "checkout"
                result, _, _ = capture(["git", "worktree", "add", "--detach", str(checkout), args.base], Path.cwd())
                if result:
                    raise ReportRefused("base-checkout")
                try:
                    dest = Path(temp) / "measurement"
                    if not collect(checkout, dest):
                        raise ReportRefused("base-measurement")
                    if json.loads((dest / "summary.json").read_bytes())["commit"] != args.base:
                        raise ReportRefused("base-measurement-identity")
                    trusted = json.loads((dest / "baseline-proposal.json").read_bytes())
                finally:
                    capture(["git", "worktree", "remove", "--force", str(checkout)], Path.cwd())
        else:
            trusted = json.loads(raw)
        candidate = json.loads(Path(BASELINE).read_bytes())
        expected = {"ruff", "ruff-format", "mypy"}
        if set(trusted) != expected or set(candidate) != expected or set(observed) != expected:
            raise ReportRefused("quality-tool-inventory")
        for tool in sorted(expected):
            baseline_gate(trusted[tool], candidate[tool], observed[tool])
        print("P1 quality baseline contains no new findings or allowances")
        return 0
    except Exception:
        print("P1 quality baseline refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
