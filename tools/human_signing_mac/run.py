"""Short launcher for the unchanged human signing CLI; arguments stay explicit."""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root / "site"), str(root / "code/src"), str(root / "code")]
runpy.run_module("tools.human_signing", run_name="__main__")
