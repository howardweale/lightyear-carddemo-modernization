"""Read every table in the disposable Compose database for CI after-state evidence."""
import argparse,json,re,subprocess
from hashlib import sha256
from pathlib import Path

COMPOSE=['docker','compose','-f','factory/carddemo-web/compose.yaml','exec','-T','postgres','psql','-X','-U','carddemo','-d','carddemo','-At','-v','ON_ERROR_STOP=1','-c']
def query(sql):return subprocess.check_output(COMPOSE+[sql],text=True,encoding='utf-8').strip()
def snapshot(directory):
    tables=query("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
    if not tables or any(not re.fullmatch('[a-z][a-z0-9_]*',t) for t in tables):raise ValueError('unexpected fixture table inventory')
    state={t:json.loads(query("SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb) FROM "+t+" t")) for t in tables}
    raw=(json.dumps(state,sort_keys=True,separators=(',',':'))+'\n').encode();digest=sha256(raw).hexdigest()
    directory.mkdir(parents=True,exist_ok=True);path=directory/(digest+'.json')
    if not path.exists():path.write_bytes(raw)
    return dict(sha256=digest,path=path.name,tables={k:sha256(json.dumps(v,sort_keys=True).encode()).hexdigest() for k,v in state.items()})
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();print(json.dumps(snapshot(args.out)))
