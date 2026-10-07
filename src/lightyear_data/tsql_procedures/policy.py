"""Explicit, hash-bound public-corpus mappings; no customer policy approval.

Mappings preserve values. Unknown types, error maps, count suppression and
unordered choices fail closed. A run-local signature is not a Tower decision.
"""
import json
import re
from copy import deepcopy
from lightyear_data.contracts import seal,content_hash
from .ledger import FAMILIES


def profile(item):
    return seal({'schema':'tsql-public-mapping/1','scope':'authored-public-traps-only',
        'procedure':item['id'],'trap_family':item['trap_family'],
        'assets':deepcopy(item['assets']), 'calling_convention':deepcopy(item['calling_convention']),
        'table_mapping':'exact schema/table/column names; inferred and explicitly flagged',
        'table_rows':'keyed where PK present; otherwise duplicate-preserving multiset',
        'result_sets':'ordered sets; rows duplicate-preserving multiset unless source declares order',
        'result_row_order':'multiset',
        'result_type_map':{'sqlserver':['167','175','231','239'],'postgresql':['25','1042','1043'],
                           'canonical':'variable-character','values':'unchanged'},
        'table_type_map':{'int':'integer','varchar(n)':'character varying(n)'},
        'identity_map':'catalogue ownership to exact schema/table/column; seed/increment/last consumed equal',
        'error_map':[], 'row_count_policy':'record; policy-decision-required when present',
        'informational_policy':'compare exact message; severity 0..10 -> PostgreSQL NOTICE/00000',
        'unordered_choice':'policy-decision-required' if item['trap_family'] in (18,25) else 'not-applicable',
        'classification_rules':{'exact-value-difference':'lossy','unmapped':'unsupported',
            'unapproved-business-choice':'policy-decision-required','representation-only':'normalized-equivalent'},
        'tower_decision_ids':[],'operator_review':'not independent attestation',
        'security_context':'not-assessed','performance_and_operability':'not-assessed'})


def validate(mapping):
    if mapping.get('schema')!='tsql-public-mapping/1' or content_hash(mapping)!=mapping.get('content_sha256'):
        raise ValueError('mapping-integrity')
    expected=profile({'id':mapping['procedure'],'trap_family':mapping['trap_family'],
                      'assets':mapping['assets'],'calling_convention':mapping['calling_convention']})
    if mapping!=expected:raise ValueError('unapproved-mapping-change')


def table_contract(state):
    result={}
    for name,t in state['tables'].items():
        columns=[]
        for c in t['columns']:
            if state['engine']=='sqlserver':
                if c[1]=='int':kind='integer'
                elif c[1]=='varchar' and c[2]>0:kind='character varying('+str(c[2])+')'
                else:raise ValueError('unmapped-table-type:'+str(c[1]))
                nullable=c[5]
            else:
                kind=c[1];nullable=not c[2]
                if c[3] or not (kind=='integer' or re.fullmatch(r'character varying\([1-9][0-9]*\)',kind)):
                    raise ValueError('unmapped-table-type:'+str(kind))
            columns.append({'name':c[0],'type':kind,'nullable':nullable})
        result[name]={'columns':columns,'primary_key':t['primary_key']}
    return result


def identity_contract(state):
    result={}
    for name,v in state['identity_sequence_state'].items():
        if state['engine']=='sqlserver':
            owner=json.loads(name)
            def integer(text):
                if not isinstance(text,str) or not re.fullmatch(r'-?[0-9]+',text):raise ValueError('identity-integer')
                return int(text)
            seed=integer(v['seed']);increment=integer(v['increment'])
            last=integer(v['last_value']) if v['last_value'] is not None else None
        else:
            owner=v['owner'];seed=v['seed'];increment=v['increment']
            if len(owner)!=3 or any(not x for x in owner):raise ValueError('sequence-owner-unmapped')
            if any(type(x) is not int for x in (seed,increment,v['last_value'])) or type(v['is_called']) is not bool:
                raise ValueError('sequence-value-type')
            last=v['last_value'] if v['is_called'] else None
            if not v['is_called'] and v['last_value']!=seed:raise ValueError('unconsumed-sequence-seed')
        key=json.dumps(owner,separators=(',',':'))
        if key in result:raise ValueError('duplicate-identity-owner')
        result[key]={'seed':seed,'increment':increment,'last_consumed':last}
    return result


def policy_register(corpus):
    return seal({'schema':'tsql-public-policy-register/1',
        'profiles':[profile(i) for i in corpus['procedures']],
        'family_rules':[{'number':n,'name':v[0],'source_requirement':v[2],
                         'scope':'public-fixture only; ASE evidence not promoted'} for n,v in FAMILIES.items()],
        'pending_decisions':['row-count suppression if present','error equivalence if both engines error',
                             'ambiguous UPDATE FROM','TOP without ORDER BY'],
        'customer_policy_approved':False,'model_calls':0})
