"""Real Linux engineering acceptance: two clean builds and public batch runs."""
from pathlib import Path
import argparse
from lightyear_mainframe.legacy_twin import build, run, receipt, PUBLIC_SCENARIOS


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    first = build(output/'build-a')
    second = build(output/'build-b')
    binaries = {k: v for k, v in first['files'].items() if '/bin/' in k}
    other = {k: v for k, v in second['files'].items() if '/bin/' in k}
    if binaries != other:
        raise AssertionError('clean builds produced different binaries; preserve both receipts')
    results = {}
    for scenario in PUBLIC_SCENARIOS:
        result = run(output/'build-a', scenario, output/'runs'/scenario)
        expected = 12 if scenario == 'intcalc-missing-disclosure' else (0, 4) if scenario == 'posttran-public' else 0
        allowed = expected if isinstance(expected, tuple) else (expected,)
        if result['returncode'] not in allowed:
            raise AssertionError(f'{scenario}: unexpected return code {result["returncode"]}')
        if scenario == 'intcalc-discriminating':
            if result['outputs']['TRANSACT']['records'] != 13:
                raise AssertionError('discriminating fixture did not exercise expected transaction output')
            lines = (output/'runs'/scenario/'after/TRANSACT').read_text().splitlines()
            if not all('2022-07-18-00.00.00.000000' in line for line in lines):
                raise AssertionError('GnuCOBOL deterministic clock did not take effect')
        results[scenario] = result
    receipt(output/'acceptance.json', phase='acceptance', reproducible_binaries=binaries,
            scenarios=results, status='engineering-executed', equivalence='not-yet-adjudicated')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
    check(p.parse_args().output)
