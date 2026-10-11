"""Execute paired public twins on Ubuntu; preserve real coverage and all gaps."""
import argparse
import json
from pathlib import Path
from lightyear_mainframe.legacy_twin import build, run, PUBLIC_SCENARIOS, receipt, new_output
from lightyear_mainframe.scenario_coverage import observe


def check(output):
    output=new_output(output)
    build(output/'control');build(output/'instrumented',instrument=True)
    rows=[]
    for scenario,(job,_) in PUBLIC_SCENARIOS.items():
        folder=output/scenario;folder.mkdir()
        control=run(output/'control',scenario,folder/'control')
        traced=run(output/'instrumented',scenario,folder/'instrumented')
        if control['outputs']!=traced['outputs'] or control['returncode']!=traced['returncode']:
            raise AssertionError('instrumentation changed output/return code: '+scenario)
        rows.append(dict(scenario=scenario,job=job,control_receipt=control['content_sha256'],
                         traced_receipt=traced['content_sha256'],scenario_adequacy=traced['scenario_adequacy']))
    groups={}
    # Baseline excludes hand-authored discriminating/rejection variants.
    for job in ('INTCALC','POSTTRAN'):
        chosen=[r['scenario'] for r in rows if r['job']==job and r['scenario'] in
                ('intcalc-public-1','intcalc-public-2','posttran-public')]
        inv=json.loads((output/'instrumented'/job/'coverage-inventory.json').read_text())
        stdout='\n'.join((output/s/'instrumented/logs/program.stdout').read_text() for s in chosen)
        groups[job]=dict(scenarios=chosen,public_only=observe(inv,stdout),
                         public_plus_generated=None,generated_status='not-run-in-instrumentation-deliverable')
    return receipt(output/'coverage-summary.json',phase='runtime-coverage',scenarios=rows,programs=groups,
                   previous_16_of_47='lexical rule-anchor overlap; not runtime coverage',
                   instrumentation_controls='all public scenario outputs and return codes identical',model_calls=0)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    check(p.parse_args().output)
