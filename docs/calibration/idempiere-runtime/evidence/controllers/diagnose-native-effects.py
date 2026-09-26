from pathlib import Path
import json,gzip,hashlib,collections
from lightyear_calibration.contracts import canonical,digest,seal,verify
from lightyear_calibration.native_catalog import read_capture
r=Path('work/native-run-20260925');out=r/'native-migrations';caps={k:read_capture(r/(k+'-catalog.json')) for k in ('oracle','postgresql')}
keys={}
for lane,cap in caps.items():
 d={k:v['rows'] for k,v in cap['results'].items()}; mapping={}
 if lane=='oracle':
  for c in d['constraints']:
   if c['constraint_type']=='P':mapping[c['table_name'].lower()]=[col['column_name'].lower() for col in sorted((v for v in d['constraint_columns'] if v['constraint_name']==c['constraint_name']),key=lambda v:v['position'])]
 else:
  attrs={(a['attrelid'],a['attnum']):a['attname'] for a in d['attributes']}
  for c in d['constraints']:
   if c['contype']=='p':mapping[c['table_name']]=[attrs[(c['conrelid'],n)] for n in c['conkey']]
 keys[lane]=mapping

def selected_rows(folder,table,expected):
 state=json.loads((folder/'state.json').read_text());verify(state);entry=state['tables'].get(table)
 if not entry:return []
 path=folder/entry['raw_file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['raw_file_sha256']
 result=[]
 with gzip.open(path,'rb') as f:
  for raw in f:
   h=hashlib.sha256(raw.rstrip(b'\n')).hexdigest()
   if h in expected:result.append(json.loads(raw))
 assert collections.Counter(digest(row) for row in result)==collections.Counter(expected)
 return result

def changes(removed,added,pk):
 a={canonical([v[k] for k in pk]).decode():v for v in removed};b={canonical([v[k] for k in pk]).decode():v for v in added}
 assert len(a)==len(removed) and len(b)==len(added)
 result={}
 for key in sorted(a.keys()|b.keys()):
  if key not in a:result[key]={'insert':b[key]}
  elif key not in b:result[key]={'delete':a[key]}
  else:
   fields={c:{'before':a[key].get(c,{'absent':True}),'after':b[key].get(c,{'absent':True})} for c in a[key].keys()|b[key].keys() if a[key].get(c,{'absent':True})!=b[key].get(c,{'absent':True})}
   result[key]={'updates':fields}
 return result

progress=json.loads((out/'progress.json').read_text());results=[];previous={'oracle':out/'entry/oracle','postgresql':out/'entry-verified/postgresql'}
for item in progress:
 case=out/f"case-{item['ordinal']:03}";comp=json.loads((case/'comparison.json').read_text());verify(comp)
 after={lane:case/('oracle-observation-retry' if lane=='oracle' and item['ordinal']==11 else lane) for lane in previous}
 tables=[]
 for table in sorted(set(comp['deltas']['oracle']['tables'])|set(comp['deltas']['postgresql']['tables'])):
  delta={lane:comp['deltas'][lane]['tables'].get(table,{'removed':{},'added':{}}) for lane in previous}
  same=delta['oracle']==delta['postgresql'];entry={'table':table,'whole_row_effects_match':same}
  if not same and keys['oracle'].get(table) and keys['oracle'][table]==keys['postgresql'].get(table):
   pk=keys['oracle'][table];ch={}
   for lane in previous:
    removed=selected_rows(previous[lane],table,delta[lane]['removed']);added=selected_rows(after[lane],table,delta[lane]['added'])
    ch[lane]=changes(removed,added,pk)
   entry.update(primary_key=pk,changed_fields_match=ch['oracle']==ch['postgresql'],changed_fields=ch)
  tables.append(entry)
 results.append({'ordinal':item['ordinal'],'script':item['script'],'comparison_sha256':comp['content_sha256'],'tables':tables})
 previous=after
result=seal({'artifact_type':'lightyear-native-effect-diagnostics','cases':results,'scope':'diagnostic separation of observed changed fields from pre-existing whole-row differences; original verdicts unchanged','native_equivalence_claim':False})
path=out/'effect-diagnostics.json';path.write_text(json.dumps(result,indent=2));print('diagnosed pairs',len(results));print('bytes',path.stat().st_size)
