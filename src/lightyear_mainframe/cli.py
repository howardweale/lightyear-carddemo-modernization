from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .arrival import dry_run
from .inventory import coverage, inventory, markdown
from .records import decode_fixed, decode_rdw, decode_record, load_copybook
from .public_corpus import verify_public


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description='COBOL source inventory and byte-preserving arrival kit')
    sub = parser.add_subparsers(dest='command', required=True)
    inv = sub.add_parser('inventory', help='inventory a pinned local public source checkout')
    inv.add_argument('--source', required=True, type=Path)
    inv.add_argument('--output', required=True, type=Path)
    dec = sub.add_parser('decode', help='decode fixed-block records using a supported copybook')
    dec.add_argument('--copybook', required=True, type=Path)
    dec.add_argument('--input', required=True, type=Path)
    dec.add_argument('--output', required=True, type=Path)
    dec.add_argument('--codec', required=True, choices=['cp037', 'cp500', 'cp1140'])
    dec.add_argument('--framing', choices=['fixed', 'record', 'rdw'], default='fixed')
    dec.add_argument('--binary-byteorder', choices=['big', 'little'])
    dec.add_argument('--binary-truncation', choices=['std', 'bin'])
    dec.add_argument('--redefines', type=Path, help='JSON mapping of overlay paths to selected names')
    dec.add_argument('--sign-policy', choices=['preferred', 'ibm-valid'], default='preferred')
    run = sub.add_parser('dry-run', help='exercise every pack job against loopback mocks')
    run.add_argument('--kit', required=True, type=Path)
    run.add_argument('--output', required=True, type=Path)
    verify = sub.add_parser('verify-public', help='decode the pinned public CardDemo EBCDIC fixtures locally')
    verify.add_argument('--source', required=True, type=Path)
    verify.add_argument('--output', required=True, type=Path)
    cov = sub.add_parser('coverage', help='bind local/simulated observations; native coverage remains unobserved')
    cov.add_argument('--inventory', required=True, type=Path)
    cov.add_argument('--receipt', type=Path)
    cov.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'inventory':
            if not args.source.is_dir(): raise ValueError('source must be an existing directory')
            result = inventory(args.source)
            if not result['programs']: raise ValueError('no COBOL programs found')
            write_json(args.output/'inventory.json', result)
            (args.output/'report.md').write_text(markdown(result), encoding='utf-8')
            write_json(args.output/'coverage-baseline.json', coverage(result))
            print(json.dumps(result['summary'], sort_keys=True))
        elif args.command == 'verify-public':
            write_json(args.output, verify_public(args.source))
        elif args.command == 'decode':
            layout = load_copybook(args.copybook)
            decoder = {'fixed': decode_fixed, 'rdw': decode_rdw, 'record': lambda *a, **kw: [decode_record(*a, **kw)]}[args.framing]
            from lightyear_calibration.contracts import read_json
            records = decoder(layout, args.input.read_bytes(), codec=args.codec, sign_policy=args.sign_policy,
                              binary_byteorder=args.binary_byteorder, binary_truncation=args.binary_truncation,
                              redefines=read_json(args.redefines) if args.redefines else None)
            write_json(args.output, dict(layout=layout.manifest(), records=records))
        elif args.command == 'dry-run':
            result = dry_run(args.kit)
            write_json(args.output, result)
            print(result['status']+'; simulated; equivalence not assessed')
        else:
            result = coverage(json.loads(args.inventory.read_text()), json.loads(args.receipt.read_text()) if args.receipt else None)
            write_json(args.output, result)
    except (ValueError, OSError, KeyError) as exc:
        print(f'mainframe: {exc}', file=sys.stderr)
        return 2
    return 0
