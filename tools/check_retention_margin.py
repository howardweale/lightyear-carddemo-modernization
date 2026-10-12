"""Measure runner free disk before any compilation; refuse inadequate margins."""
import argparse
import json
import shutil
from pathlib import Path
from lightyear_mainframe.campaign_provenance import current_binding,sealed
from lightyear_mainframe.legacy_twin import ROOT,write_json


def check(job, output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'docs/factory/retention-projection-2026-10-11.json').read_text())
    row=plan['jobs'][job];free=shutil.disk_usage(ROOT).free
    value=sealed(dict(job=job,head=current_binding()['head'],free_disk_bytes=free,
        projected_peak_bytes=row['projected_runner_peak_bytes'],disk_headroom=free/row['projected_runner_peak_bytes'],
        fresh_guard_headroom=row['fresh_guard_headroom'],targeted_guard_headroom=row['targeted_guard_headroom'],
        wall_headroom=row['wall_headroom'],projection=row))
    write_json(Path(output),value);print(json.dumps(value,indent=2))
    if min(value['disk_headroom'],value['fresh_guard_headroom'],value['targeted_guard_headroom'],value['wall_headroom'])<2:
        raise RuntimeError('retention-margin-below-twofold; no campaign started')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('job');p.add_argument('output');a=p.parse_args();check(a.job,a.output)
