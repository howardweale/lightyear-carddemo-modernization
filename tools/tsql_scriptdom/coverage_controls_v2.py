"""Nine prospective public controls; original seven-control evidence unchanged."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from .coverage_controls import controls as legacy_controls
from lightyear_data.tsql_procedures.native_evidence import sha

SCHEMAS=['dbo','business']
EXPECTED={'coverage-straight':True,'coverage-both-edges':True,'coverage-missing-edge':False,
          'coverage-handler-hit':True,'coverage-handler-missing':False,
          'coverage-scalar-declaration':True,'coverage-table-declaration':True,
          'coverage-non-dbo-schema':True,'coverage-view-excluded':True}

def controls(root):
    root=Path(root);legacy_controls(root)
    path=root/'data-modernization/tsql-procedures/corpus.json'
    corpus=json.loads(path.read_bytes());base=corpus['procedures'][0]
    for kind in ('non-dbo-schema','view-excluded'):
        item=deepcopy(base);item['id']='coverage-'+kind
        for role,asset in list(item['assets'].items()):
            sql=(root/asset['path']).read_text(encoding='utf-8')
            if kind=='non-dbo-schema':
                sql=sql.replace('dbo','business')
                if role=='source-setup':sql='CREATE SCHEMA business;\nGO\n'+sql
            elif role.endswith('setup'):
                sql+= ('\nGO\nCREATE VIEW dbo.coverage_view AS SELECT 1 AS value;\nGO\n'
                       if role=='source-setup' else '\nCREATE VIEW dbo.coverage_view AS SELECT 1 AS value;\n')
            out=path.parent/(item['id']+'-'+role+'.sql');out.write_text(sql,encoding='utf-8',newline='\n')
            item['assets'][role]={'path':out.relative_to(root).as_posix(),'sha256':sha(out.read_bytes())}
        if kind=='non-dbo-schema':
            item['calling_convention']['target']=item['calling_convention']['target'].replace('dbo','business')
        corpus['procedures'].append(item)
    for item in corpus['procedures']:
        case=deepcopy(item['cases'][0]);case.update(id='single',parameters={},repeated_runs=1)
        item['cases']=[case]
        item['calling_convention'].pop('target_parameters',None)
    corpus.update(schema='tsql-coverage-control-corpus/2',coverage_revision=2,
                  coverage_schemas=SCHEMAS,expected=EXPECTED,model_calls=0)
    path.write_text(json.dumps(corpus,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    return corpus

if __name__=='__main__':controls(Path(sys.argv[1]).resolve())
