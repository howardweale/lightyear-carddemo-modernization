"""Prospective named/typed corpus; historical parameterless assets stay intact."""
import json,re
from pathlib import Path
from .corpus import artifacts
from .native_evidence import sha,canonical
from lightyear_data.contracts import seal

# Exact authored substitutions, not a general SQL rewriter. Each declared input
# affects the reference's tested expression or stored state. Mutants keep their
# original fault even where that means ignoring an input.
RULES={
 'datetime-001':('milliseconds','int','integer',1,[('CAST(\'2026-10-01 00:00:00.001\' AS datetime)',"CAST(DATEADD(millisecond,@milliseconds,CAST('2026-10-01' AS datetime2)) AS datetime)")],[('1::numeric','milliseconds::numeric'),("timestamp '2026-10-01 00:00:00.001'","timestamp '2026-10-01'+milliseconds*interval '1 millisecond'")]),
 'datetime-002':('milliseconds','int','integer',2,[('CAST(\'2026-10-01 00:00:00.002\' AS datetime)',"CAST(DATEADD(millisecond,@milliseconds,CAST('2026-10-01' AS datetime2)) AS datetime)")],[('2::numeric','milliseconds::numeric'),("timestamp '2026-10-01 00:00:00.002'","timestamp '2026-10-01'+milliseconds*interval '1 millisecond'")]),
 'datediff-day':('finish','datetime2','timestamp','2026-10-02T00:00:00',[("'20261002 00:00:00'",'@finish')],[("date '2026-10-02'",'finish::date'),("timestamp '2026-10-02 00:00:00'",'finish')]),
 'datediff-year':('finish','datetime2','timestamp','2026-01-01T00:00:00',[("'20260101'",'@finish')],[('2026-2025','extract(year FROM finish)::integer-2025'),("date '2026-01-01'",'finish::date')]),
 'datefirst':('day_value','date','date','2026-10-04',[("'20261004'",'@day_value')],[("date '2026-10-04'",'day_value')]),
 'convert-style':('day_value','date','date','2026-04-03',[("'20260403'",'@day_value')],[("date '2026-04-03'",'day_value')]),
 'round-negative':('amount','int','integer',-150,[('-150','@amount')],[('-150','amount')]),
 'money-scale':('amount','decimal(10,5)','numeric', '1.23456',[('1.23456','@amount')],[('1.23456','amount')]),
 'scope-identity-trigger':('input_value','int','integer',7,[('VALUES(7)','VALUES(@input_value)')],[('VALUES(7)','VALUES(input_value)')]),
 'identity-rollback-gap':('input_value','int','integer',2,[('VALUES(2)','VALUES(@input_value)')],[('VALUES(2)','VALUES(input_value)')]),
 'table-variable-scope':('input_value','int','integer',1,[('VALUES(1)','VALUES(@input_value)')],[('ARRAY[1]','ARRAY[input_value]')]),
 'temp-table-scope':('input_value','int','integer',1,[('VALUES(1)','VALUES(@input_value)')],[('VALUES(1)','VALUES(input_value)')]),
 'cursor-fetch-status':('input_value','int','integer',3,[('(3)) x','(@input_value)) x')],[('(3)) x','(input_value)) x')]),
 'output-parameter':('input_value','int','integer',7,[('@answer=7','@answer=@input_value')],[('answer:=7','answer:=input_value')]),
 'default-return-code':('input_value','int','integer',1,[('@n int=1','@n int=@input_value')],[('BEGIN return_code:=','BEGIN PERFORM input_value; return_code:=')]),
 'update-from-ambiguous':('match_id','int','integer',1,[('m ON e.id=m.k;','m ON e.id=m.k WHERE e.id=@match_id;')],[('WHERE e.id=m.k;','WHERE e.id=m.k AND e.id=match_id;')]),
 'bit':('input_value','int','integer',2,[('CAST(2 AS bit)','CAST(@input_value AS bit)')],[('WHEN 2','WHEN input_value'),('2::','input_value::')]),
 'unordered-top':('input_value','int','integer',2,[('(2)) x','(@input_value)) x')],[('(2)) x','(input_value)) x')]),
 'dynamic-parameter-binding':('input_value','nvarchar(100)','text',"O'Brien",[("N'O''Brien'",'@input_value')],[("'O''Brien'",'input_value')]),
}
for name in ('catch-retains-prior-work','xact-abort','nested-transaction-rollback','rowcount-lifetime','set-trigger'):
 RULES[name]=('amount','int','integer',10,[('VALUES(1,10)','VALUES(1,@amount)')],[('VALUES(1,10)','VALUES(1,amount)')])
RULES['merge-upsert']=('amount','int','integer',20,[('VALUES(1,20)','VALUES(1,@amount)')],[('VALUES(1,20)','VALUES(1,amount)')])

def build(root):
 from .inventory import tokens
 output=artifacts(root);corpus=json.loads(output['data-modernization/tsql-procedures/corpus.json'])
 new={};prefix='data-modernization/tsql-procedures/typed-corpus-r1/'
 for item in corpus['procedures']:
  values={role:output[a['path']].decode() for role,a in item['assets'].items()}
  if item['id']=='integer-division':
   rule=None
  elif item['id'] in RULES:rule=RULES[item['id']]
  else:
   shared=set.intersection(*[set(t['value'] for t in tokens(values[role]) if t['kind']=='string') for role in ('source','correct','wrong')])
   if not shared:raise ValueError('typed-rule-missing:'+item['id'])
   literal=sorted(shared,key=lambda x:(-len(x),x))[0]
   rule=('input_value','varchar(200)','text',literal[1:-1].replace("''","'"),[(literal,'@input_value')],[(literal,'input_value')])
  if rule:
   name,typ,pgtype,seed,sr,tr=rule
   if name=='amount':
    name='arg_amount';sr=[(a,b.replace('@amount','@arg_amount')) for a,b in sr];tr=[(a,b.replace('amount','arg_amount')) for a,b in tr]
   for role,replacements in [('source',sr),('correct',tr),('wrong',tr)]:
    before=values[role]
    for old,newvalue in replacements:values[role]=values[role].replace(old,newvalue)
    if role in ('source','correct') and values[role]==before:raise ValueError('typed-replacement-missing:'+item['id']+':'+role)
   if item['id']=='informational-raiserror':
    for role in ('correct','wrong'):
     values[role]=values[role].replace('RAISE NOTICE input_value;', "RAISE NOTICE '%', input_value;").replace('RAISE EXCEPTION input_value;', "RAISE EXCEPTION '%', input_value;")
   src=values['source'];header,body=src.split('\nAS\n',1)
   header+=(',' if '@' in header else ' ')+f'@{name} {typ}'
   values['source']=header+'\nAS\n'+body
   for role in ('correct','wrong'):
    values[role]=values[role].replace('dbo.trap(',f'dbo.trap({name} {pgtype}'+(',' if not values[role].split('dbo.trap(',1)[1].startswith(')') else ''),1)
   for case in item['cases']:case['parameters'][name]=seed
   convention=item['calling_convention'];target=convention['target']
   convention['target']=target.replace('dbo.trap(', 'dbo.trap(%s'+(',' if not target.split('dbo.trap(',1)[1].startswith(')') else ''),1)
   convention['target_parameters']=[name]
   convention['source']='RPC dbo.trap'
   item['parameters']={name:seed}
  proc='trap_'+item['id'].replace('-','_')
  for role in ('source','correct','wrong'):
   values[role]=values[role].replace('dbo.trap','dbo.'+proc).replace('dbo.calculate','dbo.'+proc)
  for key in ('source','target'):item['calling_convention'][key]=item['calling_convention'][key].replace('dbo.trap','dbo.'+proc).replace('dbo.calculate','dbo.'+proc)
  for role,raw in values.items():
   path=prefix+item['id']+'/'+role+'.sql';new[path]=raw.encode();item['assets'][role]=dict(path=path,sha256=sha(new[path]))
  for scenario in item.get('coverage_scenarios',[]):
   for role,a in list(scenario['assets'].items()):
    if role in ('source','correct','wrong'):scenario['assets'][role]=item['assets'][role]
    else:
     path=prefix+item['id']+'/'+scenario['id']+'-'+role+'.sql';new[path]=output[a['path']];scenario['assets'][role]=dict(path=path,sha256=sha(new[path]))
   scenario['calling_convention']={**item['calling_convention'],**{k:v for k,v in scenario['calling_convention'].items() if k=='public_error_equivalence'}}
 corpus.pop('content_sha256',None);corpus.update(revision='named-typed-r1',historical_sources_unchanged=True)
 new[prefix+'corpus.json']=canonical(seal(corpus))+b'\n'
 return new

def write(root):
 for name,raw in build(Path(root)).items():
  p=Path(root)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
