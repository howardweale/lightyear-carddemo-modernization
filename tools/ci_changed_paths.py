"""Conservative changed-path selection for expensive CloudBank verification.
Unknown paths, incomplete diff or non-PR events run all jobs. No workflow skipped.
"""
import json
import os
from pathlib import Path
import re
import subprocess

PREFIXES = ('docs/factory/', 'src/lightyear_mainframe/', 'src/lightyear_factory/', 'spec/mainframe/')
TEST_PREFIXES = ('tests/test_posttran_', 'tests/test_scenario_', 'tests/test_generic_scenario_',
                 'tests/test_equivalence_', 'tests/test_target_retention', 'tests/test_oct12_diversity')
TOOLS = {'tools/check_factory_review.py','tools/check_equivalence_followup.py',
         'tools/aggregate_equivalence_shards.py','tools/check_posttran_attempt1_phase1.py',
         'tools/check_retention_margin.py','tools/measure_campaign_resources.py'}


def cloudbank_required(paths):
    if not paths:return True
    return any(not (p.startswith(PREFIXES + TEST_PREFIXES) or p in TOOLS) for p in paths)


def main():
    required=True;reason='non-PR or unavailable/incomplete changed-file inventory'
    try:
        event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        if 'pull_request' in event:
            pr=event['pull_request'];base=pr['base']['sha'];head=pr['head']['sha']
            if not all(re.fullmatch('[0-9a-f]{40}',s) for s in (base,head)):raise ValueError('invalid-ref')
            raw=subprocess.check_output(['git','diff','--no-renames','--name-only','-z',base+'...'+head])
            paths=raw.decode('utf-8').rstrip('\0').split('\0') if raw else []
            required=cloudbank_required(paths)
            reason='conservative full Git diff; unknown/shared/workflow changes run CloudBank'
    except (KeyError,ValueError,OSError,subprocess.CalledProcessError) as exc:
        reason+='; '+type(exc).__name__
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:stream.write('cloudbank='+str(required).lower()+'\n')
    print(json.dumps(dict(cloudbank=required,reason=reason)))

if __name__=='__main__':main()
