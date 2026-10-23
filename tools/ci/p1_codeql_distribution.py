"""Fetch the exact public CodeQL bundle in CI, verify before initialization."""
from hashlib import sha256
import os
from pathlib import Path
import sys
from urllib.request import urlopen


def main():
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("ci-only")
        path = Path(os.environ["RUNNER_TEMP"]) / "p1-codeql-bundle.tar.gz"
        total, digest = 0, sha256()
        url = "https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.27.3/codeql-bundle-linux64.tar.gz"
        with path.open("xb") as output, urlopen(url, timeout=120) as response:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 695275440:
                    raise ValueError("distribution-size")
                digest.update(block)
                output.write(block)
        if total != 695275440 or digest.hexdigest() != "64518dc413c8e7b5733fee2489e830a899bb1e3f28c8873b5869d5cc90164c5c":
            raise ValueError("distribution-binding")
        print("CodeQL bundle size and SHA-256 verified")
        return 0
    except Exception:
        print("CodeQL distribution refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
