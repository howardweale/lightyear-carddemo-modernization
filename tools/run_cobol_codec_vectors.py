"""CI-only public-vector driver; does not load any hidden bundle or expected-value oracle."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def refuse_float(_):
    raise ValueError('vector-float')


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('vector-duplicate-key')
        result[key] = value
    return result


def load(path):
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError('vector-size')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_float=refuse_float, parse_constant=refuse_float)


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError('vector-fields')


def match(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('vector-string')


def protocol(suite, profile_hash, independent):
    keys(suite, 'schema author source_basis profile_sha256 vectors')
    if suite['schema'] != 'cobol-codec-vectors/1' or suite['profile_sha256'] != profile_hash:
        raise ValueError('vector-profile')
    author = 'Claude' if independent else 'Codex'
    if suite['author'] != author or suite['source_basis'] != 'IBM Enterprise COBOL for z/OS 6.4; public inputs only':
        raise ValueError('vector-author')
    vectors = suite['vectors']
    if not isinstance(vectors, list) or not 1 <= len(vectors) <= 10000:
        raise ValueError('vector-count')
    seen = set()
    lines = []
    for vector in vectors:
        keys(vector, 'id rule operation pic usage sign bytes coefficient scale negative_zero offset capacity reload expected reference derivation sha256')
        match(vector['id'], r'[A-Z][A-Z0-9_-]{0,63}')
        if vector['id'] in seen:
            raise ValueError('vector-id-duplicate')
        seen.add(vector['id'])
        unsigned = {key: value for key, value in vector.items() if key != 'sha256'}
        if hashlib.sha256(canonical(unsigned)).hexdigest() != vector['sha256']:
            raise ValueError('vector-hash')
        if vector['rule'] not in ('R01', 'R02', 'R03', 'R04') or vector['operation'] not in ('decode', 'encode', 'numeric-class', 'arena-alias', 'arena-short-read'):
            raise ValueError('vector-operation')
        if vector['usage'] not in ('DISPLAY', 'PACKED', 'BINARY') or vector['sign'] not in ('UNSIGNED', 'TRAILING', 'LEADING', 'TRAILING_SEPARATE', 'LEADING_SEPARATE'):
            raise ValueError('vector-descriptor')
        rule = 'R01' if vector['operation'].startswith('arena-') else {'DISPLAY': 'R02', 'PACKED': 'R03', 'BINARY': 'R04'}[vector['usage']]
        if vector['rule'] != rule:
            raise ValueError('vector-rule')
        match(vector['pic'], r'[S9VP()0-9]{1,100}')
        match(vector['bytes'], r'(?:[0-9a-f]{2}){0,32}')
        match(vector['reload'], r'(?:[0-9a-f]{2}){0,32}')
        if type(vector['offset']) is not int or not 0 <= vector['offset'] <= 32 or type(vector['capacity']) is not int or not 1 <= vector['capacity'] <= 64:
            raise ValueError('vector-arena')
        match(vector['coefficient'], r'-?(?:0|[1-9][0-9]{0,17})')
        if type(vector['scale']) is not int or not -18 <= vector['scale'] <= 18 or type(vector['negative_zero']) is not bool:
            raise ValueError('vector-number')
        match(vector['expected'], r'(?:[0-9a-f]{2}){1,32}|-?[0-9]{1,18}:-?[0-9]{1,2}:(?:true|false)|true|false|REFUSED:[a-z][a-z-]{1,40}')
        keys(vector['reference'], 'version title url locator')
        if vector['reference']['version'] != '6.4':
            raise ValueError('vector-reference-version')
        match(vector['reference']['url'], r'https://(?:www\.ibm\.com/docs/|publibfp\.dhe\.ibm\.com/epubs/)[^\s]+')
        for text in (vector['reference']['title'], vector['reference']['locator'], vector['derivation']):
            if not isinstance(text, str) or not 1 <= len(text) <= 16000 or '\x00' in text:
                raise ValueError('vector-derivation')
        fields = [vector['operation'], vector['pic'], vector['usage'], vector['sign'], vector['bytes'],
                  vector['coefficient'], str(vector['scale']), str(vector['negative_zero']).lower(), vector['expected'],
                  str(vector['offset']), str(vector['capacity']), vector['reload'], vector['id']]
        lines.append('\t'.join(fields))
    return ('\n'.join(lines) + '\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--classes', type=Path, required=True)
    parser.add_argument('--independent-sha256')
    args = parser.parse_args()
    if args.independent_sha256:
        match(args.independent_sha256, '[0-9a-f]{64}')
        if hashlib.sha256(args.vectors.read_bytes()).hexdigest() != args.independent_sha256:
            raise ValueError('independent-file-hash')
    data = protocol(load(args.vectors), hashlib.sha256(args.profile.read_bytes()).hexdigest(), bool(args.independent_sha256))
    subprocess.run(['java', '-cp', str(args.classes), 'org.lightyear.cobol.RecordNumbersTest'], input=data, check=True, timeout=60)
    print('independent-codec-vectors-match' if args.independent_sha256 else 'author-codec-vectors-match-not-qualified')


if __name__ == '__main__':
    main()
