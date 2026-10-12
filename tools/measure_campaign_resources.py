"""Read-only disk inventory at the end of each campaign job, including failures."""
import argparse
import json
from pathlib import Path
import shutil
from lightyear_mainframe.campaign_provenance import sealed
from lightyear_mainframe.legacy_twin import write_json
from lightyear_mainframe.target_retention import size


def measure(campaign,output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    campaign=Path(campaign);target=campaign/'equivalence-followup'
    def read(path):
        return json.loads(path.read_text()) if path.exists() else None
    targeted=size(target);fresh=size(campaign)-targeted
    value=sealed(dict(fresh_compiled_bytes=fresh,targeted_bytes=targeted,total_bytes=fresh+targeted,
        free_disk_bytes=shutil.disk_usage(campaign.parent).free,
        fresh_usage=read(campaign/'resource-usage.json'),targeted_usage=read(target/'resource-usage.json'),
        phase_inventory_includes_manifests=True,inventory_excludes_this_external_report=True))
    write_json(Path(output),value);print(json.dumps(value,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('campaign');p.add_argument('output');a=p.parse_args();measure(a.campaign,a.output)
