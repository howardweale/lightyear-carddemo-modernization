"""Apply externally signed class/audit decisions to a new immutable overlay."""
import argparse,json
from pathlib import Path
from lightyear_mainframe.equivalence_automation import digest
from lightyear_mainframe.equivalence_reviews import apply_reviews
from lightyear_factory.tower_authority import configured_authority
from lightyear_mainframe.legacy_twin import ROOT

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('submissions',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();load=lambda name:json.loads((a.run/name).read_text())
    result=apply_reviews(load('resolutions.json'),load('class-requests.json'),load('audit-request.json'),
                         json.loads(a.submissions.read_text()),configured_authority(),
                         digest((ROOT/'src/lightyear_mainframe/equivalence_classes.py').read_bytes()))
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
