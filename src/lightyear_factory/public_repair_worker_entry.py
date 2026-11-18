"""Fixed fresh-exec entry; no environment import path or inherited credentials."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lightyear_factory.public_repair_worker import entry
    entry()
