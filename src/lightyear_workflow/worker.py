"""One fixed read-only CloudBank observation in an isolated process."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from .cloudbank import observe
from .policy import _unique_object


def main() -> int:
    job = json.loads(sys.stdin.read(65536), object_pairs_hook=_unique_object)
    if set(job) != {"root", "service", "lane"}:
        raise ValueError("Unsupported worker request")
    print(json.dumps(observe(Path(job["root"]), job["service"], job["lane"]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
