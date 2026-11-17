"""Synthetic isolation checks; no model, hidden material, signatures or activation."""
import copy
import base64
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory import graph_legacy_view as view
from lightyear_factory.contracts import ContractError


CANARY = 'SYNTHETIC_HELD_OUT_CANARY_71941'


def scan(label, raw):
    if CANARY.encode() in raw:
        raise ContractError('synthetic-canary')


def fixture():
    source = b'       01 BALANCE PIC 9(3).\n           ADD 1 TO BALANCE.\n'
    path = 'spec/public/synthetic.cbl'
    anchor = dict(path=path, line_start=1, line_end=2, excerpt_sha256=view.sha(source))
    nodes = [dict(id='legacy:field:balance', kind='cobol_field', name='BALANCE',
                 properties={'picture':'9(3)'}, anchors=[anchor], dependencies=[]),
             dict(id='legacy:program:example', kind='cobol_program', name='EXAMPLE',
                 properties={}, anchors=[anchor], dependencies=[])]
    edges = [dict(id='edge:declares', source=nodes[1]['id'], target=nodes[0]['id'], relation='DECLARES')]
    inventory = dict(schema='factory-legacy-inventory/1',customer_id='carddemo-reference',
        lane_sha256='a'*64,sources={path:view.sha(source)},nodes=nodes,edges=edges)
    raw = dict(nodes=[dict(id=n['id'],kind=n['kind'],name=n['name'],properties={}) for n in nodes],
               edges=copy.deepcopy(edges))
    return raw, inventory, {path:source}


class LegacyViewTests(unittest.TestCase):
    def projection(self, raw=None, inventory=None, sources=None):
        a,b,c=fixture()
        return view.filtered_projection(a if raw is None else raw,
            view.encoded(b if inventory is None else inventory), c if sources is None else sources, scan)

    def session(self, *, raw=None, inventory=None, sources=None, loaded=None):
        a,b,c=fixture()
        a=a if raw is None else raw; b=b if inventory is None else inventory; c=c if sources is None else sources
        clean=self.projection(a,b,c)
        invraw=view.encoded(b)
        profile=view.encoded(dict(schema='factory-legacy-profile/1',inventory_sha256=view.sha(invraw),rule_hashes=view.RULES))
        digest=view.sha(view.encoded(clean))
        manifest={'projection_sha256':digest,'policy_sha256':view.sha(profile)}
        decision={'review_after':(datetime.now(timezone.utc)+timedelta(days=1)).date().isoformat()}
        trust={'legacy_profile_sha256':view.sha(profile),'legacy_inventory_sha256':view.sha(invraw)}
        temp=self.enterContext(tempfile.TemporaryDirectory())
        with patch('lightyear_toolkit.graph_approval.load_approved',
                   return_value=(clean if loaded is None else loaded,manifest,decision)):
            return view.LegacyGraphSession(('unused','unused',trust),invraw,c,profile,scan,temp,digest)

    def test_minimal_projection_reuses_field_mode_and_source_bytes(self):
        projection=self.projection()
        self.assertEqual(projection['mode'],'field')
        self.assertEqual(projection['verified_by'],[])
        self.assertEqual(len(projection['nodes']),2)
        self.assertIn('ADD 1 TO BALANCE.',projection['nodes'][0]['source'][0]['text'])

    def test_raw_metadata_never_survives_allowlist(self):
        raw,inv,sources=fixture()
        for node in raw['nodes']:
            node.update(status='verified-candidate',source=[{'text':CANARY}],expected_output=CANARY)
            node['properties']={'status':CANARY,'statement':CANARY}
        result=self.projection(raw,inv,sources)
        self.assertNotIn(CANARY,view.encoded(result).decode())
        self.assertNotIn('verified-candidate',view.encoded(result).decode())

    def test_excluded_nodes_unreachable_by_all_four_tools(self):
        for forbidden in ('modern:answer','scenario:answer','test:answer','legacy:test:answer'):
            with self.subTest(node=forbidden):
                raw,inv,sources=fixture()
                raw['nodes'].append(dict(id=forbidden,kind='cobol_program',name='EXCLUDED_PUBLIC_NAME',
                    properties={'statement':CANARY},source=[{'text':'BALANCE '+CANARY}]))
                raw['edges'].extend([dict(id='edge:excluded',source='legacy:field:balance',
                    target=forbidden,relation='VERIFIED_BY'),dict(id='edge:implemented',
                    source='legacy:program:example',target=forbidden,relation='IMPLEMENTED_BY')])
                session=self.session(raw=raw,inventory=inv,sources=sources)
                self.assertNotIn(forbidden,session._tools.index.node_by_id)
                result=session.call('planner',0,'graph_search',{'query':'EXCLUDED_PUBLIC_NAME'})
                self.assertEqual(result['items'],[])
                for tool in ('graph_node','graph_neighbors','graph_references'):
                    with self.assertRaisesRegex(ContractError,'legacy-node-unavailable'):
                        session.call('planner',0,tool,{'node_id':forbidden})
                for tool in ('graph_node','graph_neighbors','graph_references'):
                    result=session.call('planner',0,tool,{'node_id':'legacy:field:balance'})
                    self.assertNotIn(CANARY,view.encoded(result).decode())
                    self.assertNotIn(forbidden,view.encoded(result).decode())

    def test_source_canary_is_refused_even_with_matching_inventory_hash(self):
        raw,inv,sources=fixture(); path=next(iter(sources))
        sources[path]=sources[path]+CANARY.encode()+b'\n'
        inv['sources'][path]=view.sha(sources[path])
        for node in inv['nodes']:
            node['anchors']=[dict(path=path,line_start=1,line_end=3,excerpt_sha256=view.sha(sources[path]))]
        with self.assertRaisesRegex(ContractError,'synthetic-canary'):
            self.projection(raw,inv,sources)

    def test_derived_from_excluded_node_refuses(self):
        raw,inv,sources=fixture()
        raw['edges'].append(dict(id='edge:taint',source=inv['nodes'][0]['id'],target='scenario:secret',relation='DERIVED_FROM'))
        with self.assertRaisesRegex(ContractError,'legacy-tainted-provenance'):
            self.projection(raw,inv,sources)

    def test_metadata_provenance_taint_refuses(self):
        for slot in ('node','properties'):
            raw,inv,sources=fixture()
            target=raw['nodes'][0] if slot=='node' else raw['nodes'][0]['properties']
            target['provenance_dependencies']=['modern:answer']
            with self.assertRaisesRegex(ContractError,'legacy-tainted-provenance'):
                self.projection(raw,inv,sources)

    def test_provenance_cycle_refuses(self):
        raw,inv,sources=fixture()
        inv['nodes'][0]['dependencies']=[inv['nodes'][1]['id']]
        inv['nodes'][1]['dependencies']=[inv['nodes'][0]['id']]
        with self.assertRaisesRegex(ContractError,'legacy-tainted-provenance'):
            self.projection(raw,inv,sources)

    def test_index_not_built_for_unfiltered_approved_snapshot(self):
        loaded=self.projection(); loaded['nodes'][0]['properties']['status']='verified-candidate'
        with patch('lightyear_toolkit.graph.GraphTools') as index:
            with self.assertRaisesRegex(ContractError,'legacy-approved-payload-not-filtered'):
                self.session(loaded=loaded)
            index.assert_not_called()

    def test_public_source_hash_and_anchor_mismatches_refuse(self):
        raw,inv,sources=fixture(); path=next(iter(sources))
        for where in ('source','anchor'):
            bad=copy.deepcopy(inv)
            if where=='source': bad['sources'][path]='0'*64
            else: bad['nodes'][0]['anchors'][0]['excerpt_sha256']='0'*64
            with self.assertRaises(ContractError): self.projection(raw,bad,sources)

    def test_duplicate_edges_refuse(self):
        raw,inv,sources=fixture(); raw['edges'].append(copy.deepcopy(raw['edges'][0]))
        with self.assertRaisesRegex(ContractError,'legacy-graph-edge'):
            self.projection(raw,inv,sources)

    def test_nonreviewed_rule_and_property_refuse(self):
        raw,inv,sources=fixture()
        for key,value in (('status','verified-candidate'),('expected_output',CANARY)):
            bad=copy.deepcopy(inv);bad['nodes'][0]['properties'][key]=value
            with self.assertRaisesRegex(ContractError,'legacy-properties'): self.projection(raw,bad,sources)
        inv['nodes'][0].update(id='rule:intcalc:monthly-interest',kind='business_rule',properties={'statement':'Expected result '+CANARY})
        with self.assertRaisesRegex(ContractError,'legacy-rule-text'): self.projection(raw,inv,sources)

    def test_builder_budget_and_planner_budget(self):
        session=self.session()
        for _ in range(8): session.call('planner',0,'graph_search',{'query':'BALANCE'})
        with self.assertRaisesRegex(ContractError,'legacy-call-budget'):
            session.call('planner',0,'graph_search',{'query':'BALANCE'})
        for phase in range(6):
            for _ in range(3): session.call('builder',phase,'graph_search',{'query':'BALANCE'})
            with self.assertRaisesRegex(ContractError,'legacy-call-budget'):
                session.call('builder',phase,'graph_search',{'query':'BALANCE'})
        self.assertEqual(session._count,26)

    def test_no_divergence_guidance_or_analysis_access(self):
        session=self.session()
        for role,tool in (('builder','explain_divergence'),('builder','graph_guidance'),('analysis','graph_search')):
            with self.assertRaisesRegex(ContractError,'legacy-tool-forbidden'):
                session.call(role,0,tool,{'query':'BALANCE'})

    def test_scanner_failure_poisoned_session(self):
        session=self.session()
        with self.assertRaisesRegex(ContractError,'synthetic-canary'):
            session.call('planner',0,'graph_search',{'query':CANARY})
        with self.assertRaisesRegex(ContractError,'legacy-tool-forbidden'):
            session.call('planner',0,'graph_search',{'query':'BALANCE'})

    def test_output_serializer_refuses_unapproved_fields(self):
        result=dict(projection_sha256='a'*64,truncated=False,items=[{'id':'legacy:field:x','expected_output':CANARY}],cursor=None)
        with self.assertRaisesRegex(ContractError,'legacy-result-allowlist'):
            view.output_fields('graph_node',result)

    def test_expired_approval_refuses(self):
        session=self.session()
        with patch.object(session._tools,'active',return_value=False):
            with self.assertRaisesRegex(ContractError,'legacy-approval-expired'):
                session.call('builder',0,'graph_search',{'query':'BALANCE'})

    def test_source_paths_and_strict_json(self):
        for path in ('/abs.cbl','../escape.cbl','C:/source.cbl','test.json','a\\b.cbl'):
            self.assertFalse(view.path_ok(path))
        for raw in (b'{"a":1,"a":2}',b'{"n":NaN}',b'{"n":1.2}',b'\xff'):
            with self.assertRaises(ContractError): view.strict(raw)

    def test_existing_isolation_scanner_rejects_encoded_canaries(self):
        from lightyear_factory.isolation_scan import scan as isolation_scan
        tokens={key:'legacy-synthetic-'+key+'-'+'x'*64
                for key in ('expected-state','reference-output','session-answer')}
        for token in tokens.values():
            for value in (token,base64.b64encode(token.encode()).decode(),token.encode().hex()):
                session=self.session()
                session._scanner=lambda name,raw: isolation_scan([(name,raw)],tokens,())
                with self.assertRaisesRegex(ContractError,'isolation-breach'):
                    session.call('planner',0,'graph_search',{'query':value})

    def test_each_pagination_request_spends_another_call(self):
        raw,inv,sources=fixture()
        for i in range(3):
            node=copy.deepcopy(inv['nodes'][0]);node['id']='legacy:field:extra'+str(i)
            inv['nodes'].append(node)
            raw['nodes'].append(dict(id=node['id'],kind=node['kind'],name=node['name'],properties={}))
        session=self.session(raw=raw,inventory=inv,sources=sources)
        first=session.call('builder',0,'graph_search',{'query':'BALANCE','limit':1})
        self.assertTrue(first['cursor'])
        second=session.call('builder',0,'graph_search',{'query':'BALANCE','limit':1,'cursor':first['cursor']})
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        self.assertEqual(session._count,2)
        self.assertLessEqual(len(view.encoded(second)),7168)

    def test_arguments_cannot_enable_hybrid_or_deeper_traversal(self):
        session=self.session()
        for tool,args,code in (
            ('graph_search',{'query':'BALANCE','mode':'hybrid'},'legacy-argument-fields'),
            ('graph_neighbors',{'node_id':'legacy:field:balance','depth':2},'legacy-depth'),
            ('graph_neighbors',{'node_id':'legacy:field:balance','relations':['VERIFIED_BY']},'legacy-relations')):
            with self.assertRaisesRegex(ContractError,code):session.call('builder',0,tool,args)


    def test_disclosed_excerpt_is_exact_hashed_byte_lines_with_form_feed(self):
        raw,inv,sources=fixture(); path=next(iter(sources))
        source=b'first\fstill-first\nsecond\nthird\n'
        sources[path]=source; inv['sources'][path]=view.sha(source)
        selected=b''.join(source.splitlines(keepends=True)[0:2])
        for node in inv['nodes']:
            node['anchors']=[dict(path=path,line_start=1,line_end=2,excerpt_sha256=view.sha(selected))]
        projection=self.projection(raw,inv,sources)
        for node in projection['nodes']:
            text=node['source'][0]['text']
            self.assertEqual(text.encode('utf-8'),selected)
            self.assertEqual(view.sha(text.encode('utf-8')),inv['nodes'][0]['anchors'][0]['excerpt_sha256'])
            self.assertIn('second',text)
            self.assertNotIn('third',text)

    def test_include_source_requires_exact_bool(self):
        session=self.session()
        for value in (None,0,1,'false',[],{}):
            with self.subTest(value=value), self.assertRaisesRegex(ContractError,'legacy-include-source'):
                session.call('planner',0,'graph_node',{'node_id':'legacy:field:balance','include_source':value})
        self.assertEqual(session._count,0)
        for value in (False,True):
            result=session.call('planner',0,'graph_node',{'node_id':'legacy:field:balance','include_source':value})
            self.assertEqual(bool(result['items'][0].get('source')),value)

    def test_cursor_requires_bounded_string_before_dispatch(self):
        session=self.session()
        for value in (None,0,True,[],{},'x'*513):
            with self.subTest(value=value), self.assertRaisesRegex(ContractError,'legacy-cursor'):
                session.call('planner',0,'graph_search',{'query':'BALANCE','cursor':value})
        self.assertEqual(session._count,0)
        empty=dict(projection_sha256=session.projection_sha256,truncated=False,items=[],cursor=None)
        with patch.dict(session._dispatch,{'graph_search':lambda **args: empty}):
            for value in ('','x'*512):
                self.assertEqual(session.call('planner',0,'graph_search',{'query':'BALANCE','cursor':value}),empty)


if __name__=='__main__': unittest.main()
