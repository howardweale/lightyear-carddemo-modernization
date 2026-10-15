"""Collect fresh control/traced refusals and publish a non-effective overlay in CI."""
import argparse
import json
import os
from pathlib import Path
from lightyear_mainframe.campaign_provenance import current_binding
from lightyear_mainframe.legacy_twin import build, run, write_json
from lightyear_mainframe.loader_domain import SCENARIO, loader_receipt, assess, source_binding
from lightyear_mainframe.scenario_generation import manifest


def check(campaign):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('CI-only-loader-domain-experiment')
    source_binding()  # refuse changed domain before any compilation or execution
    head = current_binding()['head']
    folder = campaign / 'loader-domain'; folder.mkdir()
    build(folder / 'control-build', jobs=['INTCALC'])
    try:
        run(folder / 'control-build', SCENARIO, folder / 'control', generated=SCENARIO)
    except RuntimeError:
        pass  # The structured receipt below must prove the exact refusal.
    control = loader_receipt(folder / 'control-build', folder / 'control', instrumented=False, head=head)
    traced = loader_receipt(campaign / 'baseline', campaign / 'cases' / SCENARIO, instrumented=True, head=head)
    rows = json.loads((campaign / 'mutation-results.json').read_bytes())
    overlay = assess(rows, [r['id'] for r in manifest() if r['job'] == 'INTCALC'], control, traced, head)
    write_json(campaign / 'loader-domain-overlay.json', overlay)
    print(json.dumps({'raw_gaps': overlay['original_gap_count'], 'resolved': sum(r['assessment'] == 'resolved-by-valid-comparisons' for r in overlay['assessments']), 'effective': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('campaign', type=Path)
    check(p.parse_args().campaign.resolve())
