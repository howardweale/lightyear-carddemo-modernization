"""Private, native A3 checkpoint derivation; never changes diagnostic captures.

Only disposable database clones may execute this module. The original admitted
checkpoint and all earlier qualification evidence remain immutable.
"""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sys

from .contracts import canonical, digest, read_json, require, seal, verify
from .native_reconciliation import state, rows

OFFSET = 10_000_000
TABLES = frozenset(('m_productprice', 'm_storageonhand', 'ad_sequence'))
SQL = (
    'UPDATE M_ProductPrice SET PriceList=PriceList*2+1, PriceStd=PriceStd*2+1, '
    'PriceLimit=PriceLimit*2+1, M_ProductPrice_ID=M_ProductPrice_ID+10000000',
    'UPDATE M_StorageOnHand SET QtyOnHand=QtyOnHand*2+3',
    "UPDATE AD_Sequence SET CurrentNext=CurrentNext+10000000 WHERE IsTableID='Y' AND IsActive='Y'",
)
RECIPE = seal({'artifact_type':'ms94-a3-private-checkpoint-recipe',
    'version':1,'statements':list(SQL),'identifier_offset':OFFSET,
    'changed_tables':sorted(TABLES),'schema_changes':False,
    'candidate_source_changes':False,'capture_rewriting':False,
    'scope':'Stored price amounts, stock quantities, price-row primary keys and future application table identifiers.'})


def number(value):
    require(type(value) is int or isinstance(value, dict) and set(value)=={'decimal'},
            'Expected captured exact native numeric value')
    result=Decimal(value if type(value) is int else value['decimal'])
    require(result.is_finite(), 'Nonfinite checkpoint value')
    return result


def verify_table(table, before, after):
    """Audit every cell; only the prospective affine transformations may differ."""
    require(table in TABLES and before and len(before)==len(after), 'Checkpoint row count differs or empty control')
    key_columns={'m_productprice':('m_productprice_id',),
                 'm_storageonhand':('m_storageonhand_uu',),
                 'ad_sequence':('ad_sequence_id',)}[table]
    def key(row, reverse=False):
        values=[row[k] for k in key_columns]
        require(all(x is not None for x in values), 'Null checkpoint row identity')
        if reverse and table=='m_productprice':
            require(type(values[0]) is int, 'Noninteger price identity')
            values[0]-=OFFSET
        return canonical(values)
    left={key(r):r for r in before};right={key(r,True):r for r in after}
    require(len(left)==len(before) and len(right)==len(after) and set(left)==set(right),
            'Checkpoint row identities or multiplicities differ')
    changed=Counter()
    for k,b in left.items():
        a=right[k];require(set(b)==set(a), 'Checkpoint row columns changed')
        for column in b:
            if table=='m_productprice' and column in ('pricelist','pricestd','pricelimit'):
                if b[column] is None:require(a[column] is None,'Null monetary cell changed')
                else:
                    require(number(a[column])==number(b[column])*2+1, 'Monetary perturbation differs')
                    require(number(a[column])!=number(b[column]), 'Monetary cell was not perturbed')
                    changed['monetary_cells']+=1
            elif table=='m_productprice' and column=='m_productprice_id':
                require(type(b[column]) is int and a[column]==b[column]+OFFSET, 'Price identifier perturbation differs')
                changed['identifier_cells']+=1
            elif table=='m_storageonhand' and column=='qtyonhand':
                require(number(a[column])==number(b[column])*2+3 and number(a[column])!=number(b[column]),
                        'Quantity perturbation differs')
                changed['quantity_cells']+=1
            elif table=='ad_sequence' and column=='currentnext' and b['istableid']=='Y' and b['isactive']=='Y':
                require(number(a[column])==number(b[column])+OFFSET, 'Application identifier sequence differs')
                changed['identifier_sequence_cells']+=1
            else:
                require(canonical(a[column])==canonical(b[column]), 'Undeclared checkpoint cell changed')
    require(sum(changed.values())>0, 'No checkpoint perturbation')
    return dict(changed)


def audit(before_folder, after_folder, lane):
    before=state(Path(before_folder),lane);after=state(Path(after_folder),lane)
    require(set(before['tables'])==set(after['tables']), 'Checkpoint table inventory changed')
    require(before['structure_query_sha256']==after['structure_query_sha256'] and
            before['row_query_contract']==after['row_query_contract'], 'Capture contract changed')
    require(canonical(before['structure'])==canonical(after['structure']), 'Checkpoint structure changed')
    counts=Counter()
    for table,b in before['tables'].items():
        a=after['tables'][table]
        require(b['rows']==a['rows'], 'Checkpoint table row count changed')
        if table in TABLES:
            counts.update(verify_table(table,rows(Path(before_folder),b),rows(Path(after_folder),a)))
        else:require(b['row_multiset']==a['row_multiset'], 'Undeclared table changed during checkpoint derivation')
    require(set(counts)=={'monetary_cells','identifier_cells','quantity_cells','identifier_sequence_cells'}
            and all(v>0 for v in counts.values()), 'Perturbation does not cover every private value class')
    return seal({'artifact_type':'ms94-a3-native-checkpoint-transform-audit','lane':lane,
                 'recipe_sha256':RECIPE['content_sha256'],'before_sha256':before['content_sha256'],
                 'after_sha256':after['content_sha256'],'structure_identical':True,
                 'row_counts_identical':True,'changed_cells':dict(counts),'passed':True})


def catalog_binding(checkpoint, observed_state):
    verify(checkpoint);verify(observed_state)
    require(checkpoint.get('admitted') is True, 'Catalog predecessor checkpoint is not admitted')
    return {'ms84_checkpoint_sha256':checkpoint['content_sha256'],
            'state_sha256':observed_state['content_sha256']}


def derive(spec):
    """Execute real SQL, then independently capture and verify the resulting DB."""
    from .journey_worker import connect, observe, write
    from .native_catalog import capture, query
    from .schema_constraint_probes import run_lane
    lane=spec['lane'];require(lane in ('oracle','postgresql'),'Unknown lane')
    require(spec['recipe_sha256']==RECIPE['content_sha256'], 'Checkpoint recipe changed')
    out=Path(spec['output']);require(not out.exists(), 'Do not replace checkpoint evidence')
    out.mkdir(parents=True)
    before=observe(lane,spec['password'],out/'before')
    expected=read_json(Path(spec['admitted_entry'])/'state.json');verify(expected)
    require({k:v['row_multiset'] for k,v in before['tables'].items()}==
            {k:v['row_multiset'] for k,v in expected['tables'].items()}, 'Derivation did not start at admitted checkpoint')
    with connect(lane,spec['password']) as c:
        if lane=='postgresql':c.autocommit=False
        with c.cursor() as cur:
            # The selected primary key has no incoming relationships. Refuse a
            # different schema instead of disabling or rewriting constraints.
            incoming=query(c,
                "SELECT COUNT(*) n FROM user_constraints f JOIN user_constraints p ON f.r_constraint_name=p.constraint_name WHERE f.constraint_type='R' AND p.table_name='M_PRODUCTPRICE'"
                if lane=='oracle' else
                "SELECT COUNT(*) n FROM pg_constraint WHERE contype='f' AND confrelid='adempiere.m_productprice'::regclass")
            require(incoming==[{'n':0}], 'Price-row identifier has incoming foreign keys')
            executed=[]
            for sql in SQL:
                cur.execute(sql);require(cur.rowcount>0,'Empty native perturbation')
                executed.append({'sql_sha256':digest(sql),'affected_rows':cur.rowcount})
        c.commit()
    after=observe(lane,spec['password'],out/'after')
    checked=audit(out/'before',out/'after',lane)
    with connect(lane,spec['password']) as c:
        predecessor=read_json(Path(spec['admitted_checkpoint']))
        cat=capture(c,lane,catalog_binding(predecessor,after))
        probes=run_lane(c,lane,isolated_test_copy=True,catalog_sha256=cat['content_sha256'])
    require(probes['expected_cases']==probes['expectations_met']==30 and
            len(probes['cases'])==30 and all(x['expectation_met'] for x in probes['cases']) and
            probes['transaction_rolled_back'] is True,'Perturbed checkpoint constraint probes failed')
    entry=observe(lane,spec['password'],out/'entry')
    require({k:v['row_multiset'] for k,v in entry['tables'].items()}==
            {k:v['row_multiset'] for k,v in after['tables'].items()},'Constraint probes changed derived checkpoint')
    require(canonical(entry['structure'])==canonical(after['structure']),'Constraint probes changed structure')
    write(out/'catalog.json',cat);write(out/'probes.json',probes);write(out/'audit.json',checked)
    result=seal({'artifact_type':'ms94-a3-native-checkpoint-derivation','lane':lane,
        'recipe_sha256':RECIPE['content_sha256'],'audit_sha256':checked['content_sha256'],
        'catalog_sha256':cat['content_sha256'],'probes_sha256':probes['content_sha256'],
        'entry_sha256':entry['content_sha256'],'statements':executed,'passed':True})
    write(out/'derivation.json',result)
    return result


if __name__=='__main__':
    print(json.dumps(derive(json.load(sys.stdin))))
