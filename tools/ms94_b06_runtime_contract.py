"""Plan-bound B06 clock collection and runtime inventory (no Docker calls)."""
from tools.ms94_b06_admission import check, utc, LANES


def runtime_contract(plan, run_id):
    expected = {
        'database-' + lane: {'container': run_id + '-operations-1-' + lane,
                            'image': plan['declaration']['environment']['engines'][lane]['image_digest']}
        for lane in LANES}
    expected['capture'] = {'container': run_id + '-operations-1-runner', 'image': plan['local']['runner_image']}
    for lane in LANES:
        expected['application-' + lane] = {'container': run_id + '-application-' + lane,
                                          'image': plan.get('built_runtime', {}).get('image', plan['local']['runner_image'])}
        if 'posting_observer' in plan:
            expected['observer-' + lane] = {'container': run_id + '-posting-observer-' + lane,
                                           'image': plan['local']['runner_image']}
        if plan.get('journey') == 'J1':
            expected['rollback-lock-observer-' + lane] = {'container': run_id + '-observer-' + lane,
                                                          'image': plan['local']['runner_image']}
    return expected


def admit_contract(plan, run_id):
    spec = plan.get('evidence_contract', {})
    check(spec.get('clock_stages') == ['before', 'after'], 'clock-stage-plan-invalid')
    check(spec.get('runtime') == runtime_contract(plan, run_id), 'runtime-plan-invalid')
    return spec


def clock_record(samples, execution, stages):
    check(isinstance(samples, list) and len(samples) == len(stages), 'clock-sample-count')
    check([s.get('stage') for s in samples] == stages, 'clock-sample-stages')
    for sample in samples:
        check(all(k in sample for k in ('host_before_utc', 'host_after_utc', 'monotonic', 'value')),
              'clock-sample-fields')
        check(type(sample['monotonic']) in (int, float), 'clock-monotonic-invalid')
        check(utc(sample['host_before_utc']) <= utc(sample['host_after_utc']), 'clock-query-bracket')
        check(sample['value'] == execution['native_clock_' + sample['stage']]['value'], 'clock-query-value-binding')
    first, last = samples[0], samples[-1]
    return {'host_start_utc': first['host_before_utc'], 'host_end_utc': last['host_before_utc'],
            'monotonic_seconds': last['monotonic'] - first['monotonic'], 'queries': samples,
            'execution_sha256': execution['content_sha256']}


def verify_runtime(records, spec):
    check(isinstance(records, list) and len(records) == len(spec['runtime']), 'runtime-clock-attestation-incomplete')
    check(all(isinstance(r, dict) and 'container' in r for r in records), 'runtime-attestation-shape')
    observed = {r['container']: r for r in records}
    expected = {r['container']: r for r in spec['runtime'].values()}
    check(len(observed) == len(records) and set(observed) == set(expected), 'runtime-clock-inventory-differs')
    check(all(r.get('image') == expected[name]['image'] and r.get('clock_manipulation_environment') is False and
              r.get('privileged') is False and r.get('sys_time_capability') is False
              for name, r in observed.items()), 'runtime-clock-manipulation-or-image')
