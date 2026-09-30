"""Restore an admitted derived checkpoint by applying its frozen native recipe.

This runs only on a fresh disposable seed clone, before normal schema/entry
preparation. All resulting row multisets must equal the separately admitted
native checkpoint. No observations or candidate outputs are rewritten.
"""
import json
from pathlib import Path
import sys
from .contracts import read_json,require,seal
from .journey_worker import connect,observe,write
from .native_catalog import query
from .ms94_a3_checkpoint_v2 import RECIPE,SQL,audit


def restore(spec):
    lane=spec['lane'];require(lane in ('oracle','postgresql'),'Unknown lane')
    require(spec['recipe_sha256']==RECIPE['content_sha256'],'Wrong native recipe')
    out=Path(spec['output']);require(not out.exists(),'No checkpoint restore may restart')
    out.mkdir(parents=True)
    before=observe(lane,spec['password'],out/'before')
    require({k:v['row_multiset'] for k,v in before['tables'].items()}==read_json(Path(spec['base_multisets'])),
            'Restore must start at exact original admitted rows')
    with connect(lane,spec['password']) as c:
        if lane=='postgresql':c.autocommit=False
        incoming=query(c,
            "SELECT COUNT(*) n FROM user_constraints f JOIN user_constraints p ON f.r_constraint_name=p.constraint_name WHERE f.constraint_type='R' AND p.table_name='M_PRODUCTPRICE'"
            if lane=='oracle' else
            "SELECT COUNT(*) n FROM pg_constraint WHERE contype='f' AND confrelid='adempiere.m_productprice'::regclass")
        require(incoming==[{'n':0}],'Price-row identifier has incoming foreign keys')
        with c.cursor() as cur:
            for sql in SQL:
                cur.execute(sql);require(cur.rowcount>0,'Empty native restore mutation')
        c.commit()
    after=observe(lane,spec['password'],out/'after')
    checked=audit(out/'before',out/'after',lane)
    require({k:v['row_multiset'] for k,v in after['tables'].items()}==read_json(Path(spec['derived_multisets'])),
            'Native restore differs from separately admitted checkpoint')
    value=seal({'artifact_type':'ms94-a3-native-checkpoint-restore','lane':lane,
                'recipe_sha256':RECIPE['content_sha256'],'audit':checked,
                'exact_admitted_multisets':True,'passed':True})
    write(out/'restore.json',value);return value


if __name__=='__main__':print(json.dumps(restore(json.load(sys.stdin))))
