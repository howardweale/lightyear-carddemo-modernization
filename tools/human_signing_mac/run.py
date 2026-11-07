"""Short launcher for the unchanged human signing CLI; arguments stay explicit."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root / "site"), str(root / "code/src"), str(root / "code")]
from tools.human_signing import main

if __name__ == "__main__":
    raise SystemExit(main())
