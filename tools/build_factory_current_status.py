"""Render current status from the newest verified release and activation records."""
import argparse
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from tools.release_status_records import ROOT, inputs, load, render

INPUTS = inputs()


def generate(root=ROOT):
    return render(load(root))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    view, text = generate()
    for name, content in {'current-status.json': json.dumps(view, indent=2)+'\n', 'current-status.md': text}.items():
        path = ROOT/'docs/factory'/name
        if args.check:
            if path.read_text(encoding='utf-8') != content:
                raise SystemExit('stale current status: '+str(path))
        else:
            path.write_text(content, encoding='utf-8', newline='\n')
