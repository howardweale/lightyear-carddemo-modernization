"""Run public data proof in a new, explicitly named PostgreSQL schema."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from .plan import build,export
from .proof import run
from .schema import quote


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('spec/modernization/carddemo-data'))
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--schema',required=True)
    parser.add_argument('--dsn-env',default='CARDDEMO_DATA_DSN')
    args=parser.parse_args()
    if args.out.exists():raise SystemExit('output exists; use a fresh evidence directory')
    plan,entries=build(args.source)
    import psycopg
    # No DROP or overwrite. CREATE SCHEMA refuses an existing target.
    with psycopg.connect(os.environ[args.dsn_env]) as connection:
        connection.execute('CREATE SCHEMA '+quote(args.schema))
        connection.execute('SET LOCAL search_path TO '+quote(args.schema))
        receipt=run(connection,args.source,plan,entries)
    export(plan,args.out)
    root=Path(__file__).resolve().parents[3]
    receipt['implementation_files']={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    receipt.pop('content_sha256',None)
    receipt['content_sha256']=sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (args.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    lines=['# CardDemo data component proof','',f"Scope: {receipt['claim_scope']}. Overall verdict: **{receipt['verdict']}**.",'',
           '| File | Input | Loaded | Quarantined | Round trip | Reconciliation | Browse |',
           '| --- | ---: | ---: | ---: | --- | --- | --- |']
    for r in receipt['vsam']:
        lines.append(f"| {r['table']} | {r['records']} | {r['loaded']} | {r['quarantined']} | {r['round_trip']['matched']}/{r['round_trip']['compared']} {r['round_trip']['verdict']} | {r['reconciliation']['verdict']} | {r['browse_order']['matched']}/{r['browse_order']['compared']} {r['browse_order']['verdict']} |")
    lines += ['', 'IMS generated traversal: '+receipt['ims']['traversal']['verdict']+'. Public IMS unload and DL/I replay: indeterminate.',
              '', 'Screens: zero sessions compared; mutation catch rate not measured. No z/OS or customer-release claim.',
              '', 'Quarantined records require review. The receipt is unsigned and does not authorize release.']
    (args.out/'receipt.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'verdict':receipt['verdict'],'files':len(receipt['vsam']),'quarantined':receipt['quarantined'],'failures':receipt['failures']}))
    if receipt['failures'] or receipt['ims']['traversal']['verdict']!='equivalent':raise SystemExit(1)


if __name__=='__main__':main()
