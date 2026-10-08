"""Public result-order controls; no engine invocation in this generator."""
from copy import deepcopy
from pathlib import Path
import json
from lightyear_data.tsql_procedures.native_evidence import sha,canonical

def controls(root, template):
 root=Path(root);folder=root/'data-modernization/tsql-procedures/order-controls-r3';folder.mkdir(parents=True,exist_ok=False)
 base=json.loads(Path(template).read_bytes())['procedures'][0];items=[]
 setup_sql='CREATE TABLE dbo.items(id int NOT NULL PRIMARY KEY); INSERT dbo.items VALUES (1),(2);'
 setup_pg='CREATE SCHEMA dbo; CREATE TABLE dbo.items(id integer NOT NULL PRIMARY KEY); INSERT INTO dbo.items VALUES (1),(2);'
 for name,source,correct,wrong,policy in [
  ('orderless-twin','SELECT id AS value FROM dbo.items ORDER BY id','SELECT id FROM dbo.items ORDER BY id','SELECT id FROM dbo.items',False),
  ('ordered-union','SELECT id AS value FROM dbo.items UNION SELECT id FROM dbo.items ORDER BY value','SELECT id FROM dbo.items UNION SELECT id FROM dbo.items ORDER BY id','SELECT id FROM dbo.items UNION SELECT id FROM dbo.items ORDER BY id DESC',False),
  ('qualified-sort','SELECT h.id AS value FROM dbo.items h JOIN dbo.items d ON h.id=3-d.id ORDER BY d.id','SELECT h.id FROM dbo.items h JOIN dbo.items d ON h.id=3-d.id ORDER BY d.id','SELECT h.id FROM dbo.items h JOIN dbo.items d ON h.id=3-d.id ORDER BY h.id',True),
  ('nonreturning-select','SELECT id INTO #ignored FROM dbo.items; SELECT id AS value FROM dbo.items ORDER BY id','SELECT id FROM dbo.items ORDER BY id','SELECT id FROM dbo.items ORDER BY id DESC',False)]:
  item=deepcopy(base);item.update(id=name,trap_family=26,trap_name='result-order',mutation='public result-order regression',coverage_scenarios=[])
  proc='trap_'+name.replace('-','_');source='CREATE PROCEDURE dbo.'+proc+' AS BEGIN SET NOCOUNT ON; '+source+'; END;'
  def pg(query):return 'CREATE FUNCTION dbo.'+proc+'() RETURNS TABLE(value integer) LANGUAGE plpgsql AS $$ BEGIN RETURN QUERY '+query+'; END $$;'
  assets={'source':source,'correct':pg(correct),'wrong':pg(wrong),'source-setup':setup_sql,'target-setup':setup_pg,'wrong-setup':setup_pg}
  item['assets']={}
  for role,sql in assets.items():
   path=folder/(name+'-'+role+'.sql');path.write_text(sql+'\n',encoding='utf-8');item['assets'][role]=dict(path=path.relative_to(root).as_posix(),sha256=sha(path.read_bytes()))
  item['calling_convention'].update(source='RPC dbo.'+proc,target='SELECT * FROM dbo.'+proc+'()',target_parameters=[],result_columns=[dict(name='value',canonical_type='integer')])
  item['cases'][0].update(parameters={},repeated_runs=1);item['parameters']={};item['expected'].update(policy_required=policy,trap_family=26)
  items.append(item)
 body=dict(schema='tsql-order-controls/1',procedures=items,model_calls=0,claim='public adversarial controls, not M0 corpus replacement')
 path=folder/'corpus.json';path.write_bytes(canonical(body));return path
if __name__=='__main__':
 import sys
 print(controls(sys.argv[1],sys.argv[2]))
