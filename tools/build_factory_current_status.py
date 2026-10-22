"""Render current status from the newest verified release and activation records."""
import argparse
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import os
from tools.release_status_records import ROOT, inputs, load, render

INPUTS = inputs()


def generate(root=ROOT):
    model = load(root)
    snapshot = os.environ.get('LIGHTYEAR_FACTORY_LIVE_STATUS')
    if snapshot:
        from tools.release_status_records import validate_live_status
        model['live_ci'] = validate_live_status(json.loads(Path(snapshot).read_bytes()))
    return render(model)


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
