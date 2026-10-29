"""CI-only original real-clock observations; no admission or qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from tools.ci import p5_real_clock_deadline as probe


SOURCES = (
    'tools/ci/p5_real_clock_collector.py', 'tests/test_p5_real_clock_collector.py',
    'tools/ci/p5_real_clock_deadline.py', 'tests/test_p5_real_clock_deadline.py',
    'src/lightyear_factory/orchestrator.py', 'src/lightyear_factory/contracts.py',
    'src/lightyear_factory/gates.py', 'src/lightyear_factory/agents.py',
    'src/lightyear_factory/providers.py', 'src/lightyear_factory/budgeted_providers.py',
    'src/lightyear_factory/ledger.py', 'src/lightyear_factory/workspace.py',
    'src/lightyear_execution/backend.py',
)


def _save(path, value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(path=path.name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def collect(repository, output):
    repository, output = Path(repository), Path(output)
    if os.environ.get('GITHUB_ACTIONS') != 'true' or output.exists():
        raise ValueError('p5-real-clock-collector-ci-exclusive-output')
    sources = {name: hashlib.sha256((repository/name).read_bytes()).hexdigest() for name in SOURCES}
    output.mkdir(parents=True)
    report = dict(schema='p5-real-clock-collection/1',
        commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
        source_sha256=sources, production_controller_receipt=False, strict_qualified=False,
        admission_verified=False, signing=False, real_model_calls=0,
        scope='Unsigned scripted controller; actual monotonic deadline observation only',
        gaps=['No genuine admitted controller outcome or production build receipt.',
              'No physical count/generation transport or provider billing evidence.'], cases=[])
    for name, expired in (('clean', False), ('expired', True)):
        row = dict(id=name, expectation_met=False)
        try:
            observed = probe.observe(output/name, expired)
            # Save even an invalid returned observation for diagnosis; never relabel it.
            row['observation'] = _save(output/(name+'-observation.json'), observed)
            row['expectation_met'] = (probe.validate(observed) is True
                                      and observed.get('expired') is expired)
        except Exception as error:
            row['harness_error'] = type(error).__name__+': '+str(error)
        report['cases'].append(row)
    report['complete'] = all(row['expectation_met'] is True and 'harness_error' not in row
                             for row in report['cases'])
    _save(output/'report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    report = collect(args.repository, args.output)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
