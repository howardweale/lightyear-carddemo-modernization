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
        expected = 12 if scenario == 'intcalc-missing-disclosure' else (0, 4) if scenario.startswith('posttran-') else 0
        allowed = expected if isinstance(expected, tuple) else (expected,)
        if result['returncode'] not in allowed:
            raise AssertionError(f'{scenario}: unexpected return code {result["returncode"]}')
        if scenario == 'intcalc-discriminating':
            if result['outputs']['TRANSACT']['records'] != 13:
                raise AssertionError('discriminating fixture did not exercise expected transaction output')
            lines = (output/'runs'/scenario/'after/TRANSACT').read_text().splitlines()
            if not all('2022-07-18-00.00.00.000000' in line for line in lines):
                raise AssertionError('GnuCOBOL deterministic clock did not take effect')
        if scenario.startswith('posttran-'):
            if not result['invariants']['passed']:
                raise AssertionError('POSTTRAN invariant failure: preserve unresolved observations')
            if scenario != 'posttran-public':
                from lightyear_mainframe.posttran_invariants import records
                reason={'posttran-missing-card':100,'posttran-missing-account':101,'posttran-expired-account':103}[scenario]
                rows=records({'DALYREJS':(output/'runs'/scenario/'after/DALYREJS').read_bytes()},'DALYREJS')
                if len(rows)!=1 or int(rows[0]['WS-VALIDATION-FAIL-REASON'])!=reason:
                    raise AssertionError('Actual twin did not exercise intended rejection reason')
            repeat = run(output/'build-a', scenario, output/'runs'/(scenario+'-repeat'))
            if result['outputs'] != repeat['outputs']:
                raise AssertionError('POSTTRAN repeat output bytes differ')
            result = dict(result, repeatability='byte-identical', repeat_receipt=repeat['content_sha256'])
        results[scenario] = result
    receipt(output/'acceptance.json', phase='acceptance', reproducible_binaries=binaries,
            scenarios=results, status='engineering-executed', equivalence='not-yet-adjudicated')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
    check(p.parse_args().output)
