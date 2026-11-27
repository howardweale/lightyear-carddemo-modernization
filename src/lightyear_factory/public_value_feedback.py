"""Bounded observations for the authenticated, 16-case public INTCALC suite."""
import base64
import itertools
import json
import re

from lightyear_factory import public_repair_controller as ctl

SUITE = '6da875e28f95409290f77363c135ef98af395fe3448c9bf3e3da28b4cad370b2'
KEY = 'fb51317ab1f5bba9677e543133364b34e893babcac279519b6f743d9568f3b37'
IDS = tuple(f'PC-{n:02d}' for n in range(1, 17))
WIDTH = {'ACCTFILE': 300, 'TRANSACT': 350}
ABENDS = {'PC-10', 'PC-11', 'PC-12'}
CHANNELS = ('stdout', 'stderr', *WIDTH)
SCHEMA = 'public-case-feedback/2'
CAP = 8192
ROWS = 32
LINE_BYTES = 256
POLICY = dict(schema=SCHEMA, public_suite=SUITE, answer_manifest=KEY, bytes_max=CAP,
              rows_max=ROWS, line_prefix_bytes=LINE_BYTES, record_widths=WIDTH,
              priority=['exits', 'first-stream-lines', 'first-records', 'additional-lines'],
              compiler_feedback=ctl.FEEDBACK_HASH)
HASH = ctl.digest(POLICY)
# Refuse to project host paths or credential-like text even when printed by a public candidate.
SENSITIVE = re.compile(r'(?:(?<![A-Za-z0-9])/(?:[^\s/]+/|Users\b|home\b|tmp\b)|[A-Za-z]:[\\/]|\\\\|'
                       r'sk-[A-Za-z0-9_-]+|gh[pousr]_|github_pat_|'
                       r'authorization\s*[:=]|bearer\s|password\s*[:=]|-----BEGIN|age-secret-key-1)', re.I)


def check(ok):
    ctl.require(ok, 'feedback-row')


def number(n, lo, hi):
    return type(n) is int and lo <= n <= hi


def sensitive(raw):
    return any(SENSITIVE.search(raw.decode(codec, 'replace')) for codec in ('ascii', 'cp037'))


def value(raw, lf, stream):
    if raw is None:
        return None
    if sensitive(raw):
        return {'bytes': len(raw), 'redacted': True}
    if stream:
        prefix = raw[:LINE_BYTES]
        text = prefix.decode('latin-1')
        descriptor = dict(bytes=len(raw), lf=lf, clipped=len(raw) > LINE_BYTES)
        if len(ctl.canonical(text)) <= len(prefix) * 4 // 3 + 6:
            descriptor['text'] = text
        else:
            descriptor['base64'] = base64.b64encode(prefix).decode('ascii')
        return descriptor
    return dict(bytes=len(raw), base64=base64.b64encode(raw).decode('ascii'))


def pieces(raw, channel):
    if channel in WIDTH:
        width = WIDTH[channel]
        for pos in range(0, len(raw), width):
            yield raw[pos:pos + width], False
    else:
        pos = 0
        while pos < len(raw):
            end = raw.find(b'\n', pos)
            if end < 0:
                yield raw[pos:], False
                break
            yield raw[pos:end], True
            pos = end + 1


def samples(case, channel, expected, actual):
    missing = (None, False)
    for index, (left, right) in enumerate(itertools.zip_longest(
            pieces(expected, channel), pieces(actual, channel), fillvalue=missing), 1):
        if left != right:
            yield case, channel, index, left, right


def envelope(candidate, cases, observations, receipts, suite, key):
    check(suite == SUITE and key == KEY and ctl.hash_ok(candidate))
    check(len(cases) == len(observations) == len(receipts) == len(IDS))
    result = dict(schema=SCHEMA, candidate_sha256=candidate, public_suite_sha256=suite,
                  answer_manifest_sha256=key, kind='PUBLIC_DIVERGENCE', outcomes='',
                  exits={}, samples=[], omitted={ch: 0 for ch in CHANNELS}, truncated=False)
    first = {ch: [] for ch in CHANNELS}
    later = {}
    for case, spec, observation, receipt in zip(IDS, cases, observations, receipts):
        expected, actual, files, limited = observation
        check(expected is spec['expected'] and files is (case not in ABENDS))
        check(receipt['index'] == IDS.index(case))
        channels = CHANNELS if files else CHANNELS[:2]
        equal = all(expected[k] == actual[k] for k in (*channels, 'exit'))
        timeout, capped = receipt['timed_out'], receipt['output_capped']
        check(limited == (timeout or capped))
        state = ('B' if timeout and capped else 'T' if timeout else 'C' if capped
                 else 'M' if equal else 'D')
        result['outcomes'] += state
        if state == 'M':
            continue
        result['exits'][case] = [expected['exit'], actual['exit']]
        for ch in channels:
            # Stream every difference to count omissions; retain bounded prefixes of the iterator.
            extras = []
            for count, item in enumerate(samples(case, ch, expected[ch], actual[ch])):
                result['omitted'][ch] += 1
                if count == 0:
                    first[ch].append(item)
                elif ch not in WIDTH and len(extras) < ROWS:
                    extras.append(item)
            if extras:
                later[case, ch] = extras

    priority = itertools.chain(*(first[ch] for ch in CHANNELS))
    rounds = itertools.zip_longest(*later.values())
    secondary = (item for layer in rounds for item in layer if item is not None)
    for case, ch, n, left, right in itertools.chain(priority, secondary):
        if len(result['samples']) + len(result['exits']) == ROWS:
            break
        stream = ch not in WIDTH
        row = dict(case=case, channel=ch, index=n, expected=value(*left, stream), actual=value(*right, stream))
        if not stream:
            expected, actual = observations[IDS.index(case)][:2]
            row['file_bytes'] = [len(expected[ch]), len(actual[ch])]
        result['samples'].append(row)
        result['omitted'][ch] -= 1
        # False occupies one more byte than true. Reserve it until all rows are considered.
        if len(ctl.canonical(result)) > CAP:
            result['samples'].pop()
            result['omitted'][ch] += 1
    result['truncated'] = any(result['omitted'].values()) or any(
        side and (side.get('clipped') or side.get('redacted'))
        for row in result['samples'] for side in (row['expected'], row['actual']))
    return validate(result, candidate, suite, 'PUBLIC_DIVERGENCE')


def validate_side(side, ch):
    if side is None:
        return
    check(type(side) is dict and number(side.get('bytes'), 0, 8 * 1024 * 1024))
    n = side['bytes']
    if ch in WIDTH:
        check(0 < n <= WIDTH[ch])
    if set(side) == {'bytes', 'redacted'}:
        check(side['redacted'] is True)
    elif ch in WIDTH:
        check(set(side) == {'bytes', 'base64'} and type(side['base64']) is str)
        try:
            raw = base64.b64decode(side['base64'], validate=True)
        except ValueError:
            check(False)
        check(len(raw) == n and base64.b64encode(raw).decode() == side['base64'] and not sensitive(raw))
    else:
        check('lf' in side and 'clipped' in side)
        check(type(side['lf']) is bool and side['clipped'] is (n > LINE_BYTES))
        prefix = min(n, LINE_BYTES)
        if 'text' in side:
            check(set(side) == {'bytes', 'text', 'lf', 'clipped'} and type(side['text']) is str)
            check(len(side['text']) == prefix and all(ord(c) <= 255 for c in side['text'])
                  and not sensitive(side['text'].encode('latin-1')))
        else:
            check(set(side) == {'bytes', 'base64', 'lf', 'clipped'} and type(side['base64']) is str)
            try:
                raw = base64.b64decode(side['base64'], validate=True)
            except ValueError:
                check(False)
            check(len(raw) == prefix and base64.b64encode(raw).decode() == side['base64']
                  and not sensitive(raw))


def validate(row, candidate, suite, kind):
    if kind == 'COMPILE_FAILED':
        return ctl.validate_feedback(row, candidate, suite, kind)
    ctl.shape(row, 'schema kind candidate_sha256 public_suite_sha256 answer_manifest_sha256 '
              'outcomes exits samples omitted truncated', 'feedback-shape')
    ctl.require(kind == row['kind'] == 'PUBLIC_DIVERGENCE' and row['schema'] == SCHEMA
                and ctl.hash_ok(candidate) and row['candidate_sha256'] == candidate
                and row['public_suite_sha256'] == suite == SUITE and row['answer_manifest_sha256'] == KEY,
                'feedback-join')
    ctl.require(len(ctl.canonical(row)) <= CAP, 'feedback-cap')
    states = row['outcomes']
    check(type(states) is str and len(states) == 16 and set(states) <= set('MDTCB'))
    failed = {case for case, state in zip(IDS, states) if state != 'M'}
    check(type(row['exits']) is dict and set(row['exits']) == failed)
    for case, pair in row['exits'].items():
        check(type(pair) is list and len(pair) == 2 and all(number(x, -2147483648, 2147483647) for x in pair))
        check(pair[0] == (12 if case in ABENDS else 0))
    check(type(row['samples']) is list and len(row['samples']) + len(failed) <= ROWS)
    check(type(row['omitted']) is dict and set(row['omitted']) == set(CHANNELS)
          and all(number(x, 0, 16 * 8 * 1024 * 1024) for x in row['omitted'].values()))
    seen = set()
    truncated = any(row['omitted'].values())
    for sample in row['samples']:
        check(type(sample) is dict and type(sample.get('channel')) is str)
        fields = 'case channel index expected actual'
        ctl.shape(sample, fields + (' file_bytes' if sample['channel'] in WIDTH else ''), 'feedback-row')
        case, ch, index = sample['case'], sample['channel'], sample['index']
        check(type(case) is str and case in failed and type(ch) is str and ch in CHANNELS
              and number(index, 1, 8 * 1024 * 1024) and (case not in ABENDS or ch not in WIDTH))
        check((case, ch, index) not in seen and (sample['expected'] is not None or sample['actual'] is not None))
        seen.add((case, ch, index))
        if ch in WIDTH:
            sizes = sample['file_bytes']
            check(type(sizes) is list and len(sizes) == 2 and all(number(n, 0, 8 * 1024 * 1024) for n in sizes))
            check(sizes[0] % WIDTH[ch] == 0)
            for total, side in zip(sizes, (sample['expected'], sample['actual'])):
                length = max(0, min(WIDTH[ch], total - (index - 1) * WIDTH[ch]))
                check((side is None and length == 0) or
                      (type(side) is dict and length > 0 and side.get('bytes') == length))
        for side in (sample['expected'], sample['actual']):
            validate_side(side, ch)
            if side and (side.get('clipped') or side.get('redacted')):
                truncated = True
    check(row['truncated'] is truncated)
    return json.loads(ctl.canonical(row))
