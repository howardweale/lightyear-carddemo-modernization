"""Synthetic provider ports + real G2 legacy session; no live activation or calls."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from lightyear_factory import graph_repair_controller as g
from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_evaluator_adapter as adapter
from lightyear_factory.contracts import ContractError
import test_public_repair_controller as base
import test_graph_legacy_view as legacy


class Ports(base.Ports):
    def __init__(self, scores=(16,), compile_fail=()):
        super().__init__(scores,compile_fail)
        self.query_mode = 'normal'
        self.graph_fault = None
        self.graph_calls = []
        self.query_mutation = None
        self.clock = base.Clock()

    def generate(self,request,deadline):
        if request['role'] != 'graph-query':
            return super().generate(request,deadline)
        self.requests.append(copy.deepcopy(request))
        intent = dict(tool='graph_search',arguments=dict(query='BALANCE',limit=1))
        mode = self.query_mode
        if mode=='done':
            intent = dict(tool='done',arguments={})
        if mode=='late-limit' and request['turn']==1:
            mode='normal'
        response = dict(status='OUTPUT_LIMIT' if mode in ('limit','late-limit') else 'COMPLETED',
            artifact=None if mode in ('limit','late-limit') else intent,
            input_tokens=100,output_tokens=8192 if mode in ('limit','late-limit') else 20,
            model=c.MODEL,service_tier='flex',request_sha256=c.digest(request),receipt_sha256=base.H)
        if self.query_mutation:
            self.query_mutation(response)
        return response

    def graph_call(self,session,role,phase,tool,arguments,deadline,result_cap):
        self.graph_calls.append((role,phase,tool,arguments,deadline,result_cap))
        if self.graph_fault:
            raise self.graph_fault
        return session.call(role,phase,tool,arguments,result_cap=result_cap)


def binding(session,context=base.CONTEXT):
    row=base.binding(context)
    row.update(schema='graph-repair-binding/1',graph_mode='on',window_seconds=g.WINDOW,
        cap_microdollars=g.CEILING,graph_projection_sha256=session.projection_sha256,
        graph_inventory_sha256=session.inventory_sha256,graph_profile_sha256=session.profile_sha256,
        graph_authority_sha256=session.approval_sha256,query_policy_sha256=g.QUERY_HASH)
    return row


class GraphRepairTests(unittest.TestCase):
    def make(self,ports=None,context=base.CONTEXT):
        fixture=legacy.LegacyViewTests()
        self.addCleanup(fixture.doCleanups)
        session=fixture.session()
        ports=ports or Ports()
        return g.GraphController(ports,binding(session,context),context,session,ports.clock),ports

    def test_all_26_queries_five_repairs_exact_total(self):
        controller,ports=self.make(Ports((1,2,3,4,5,6)))
        result=controller.run()
        self.assertEqual(result['status'],'PUBLIC_FAIL')
        self.assertEqual(result['graph_query_turns'],26)
        self.assertEqual(result['graph_calls'],26)
        self.assertEqual(len(ports.requests),38)
        self.assertEqual(result['reserved_microdollars'],50099456)
        self.assertLessEqual(result['reserved_microdollars'],51000000)
        self.assertEqual(controller.end,controller.start+26880)
        self.assertEqual(ports.hidden_calls,[])
        self.assertEqual(result,ports.records['result'])
        self.assertEqual(result['graph_binding']['query_policy_sha256'],g.QUERY_HASH)

    def test_prior_results_visible_and_phase_history_resets(self):
        controller,ports=self.make()
        controller.run()
        queries=[r for r in ports.requests if r['role']=='graph-query']
        self.assertEqual([len(r['previous']) for r in queries],list(range(8))+list(range(3)))
        self.assertEqual(queries[1]['previous'][0],ports.records['graph-planner-0-1-tool-response'])
        self.assertEqual(queries[8]['previous'],[])
        self.assertEqual(len(ports.hidden_calls),1)
        self.assertTrue(ports.closed)

    def test_feedback_current_candidate_only_in_repair_queries(self):
        controller,ports=self.make(Ports((7,2,16)))
        controller.run()
        queries=[r for r in ports.requests if r['role']=='graph-query']
        for row in queries:
            if row['query_role']=='builder' and row['phase']:
                self.assertEqual(row['feedback'],ports.records['public-feedback-0'])
                self.assertEqual(row['candidate_sha256'],row['feedback']['candidate_sha256'])
                self.assertNotIn('feedback_history',row)
            else:
                self.assertNotIn('feedback',row)
        repair=next(r for r in queries if r['phase']==1)
        self.assertTrue(repair['plan']['text'])
        self.assertTrue(repair['analysis']['text'])
        self.assertTrue(repair['source']['text'])

    def test_compile_feedback_is_available_for_first_repair_query(self):
        controller,ports=self.make(Ports((16,),compile_fail=(0,)))
        controller.run()
        row=next(r for r in ports.requests if r.get('phase')==1)
        self.assertEqual(row['feedback']['kind'],'COMPILE_FAILED')

    def test_done_stops_queries_without_discarding_earlier_results(self):
        controller,ports=self.make()
        original=ports.generate
        def done_after_one(request,deadline):
            row=original(request,deadline)
            if request['role']=='graph-query' and request['turn']==2:
                row['artifact']=dict(tool='done',arguments={})
            return row
        ports.generate=done_after_one
        controller.run()
        self.assertEqual(controller.graph_calls,2)
        self.assertTrue(ports.records['graph-planner-0-capsule']['capsule']['responses'])

    def test_accounted_output_limit_degrades_only_this_phase(self):
        controller,ports=self.make()
        ports.query_mode='late-limit'
        controller.run()
        for phase in ('planner','builder'):
            row=ports.records['graph-'+phase+'-0-capsule']
            self.assertTrue(row['degraded'])
            self.assertEqual(row['capsule']['responses'],[])
            self.assertEqual(len(row['dropped']),1)
        self.assertEqual(controller.query_turns,4)
        self.assertGreater(controller.reserved,4224000)
        self.assertEqual(len(ports.hidden_calls),1)

    def test_unknown_send_stops_no_retry_or_hidden(self):
        controller,ports=self.make()
        ports.fail='count'
        with self.assertRaises(RuntimeError):controller.run()
        self.assertEqual(len(ports.counts),1)
        self.assertEqual(ports.hidden_calls,[])
        self.assertIn('stopped',ports.records)
        self.assertTrue(ports.closed)

    def test_malformed_query_response_refuses(self):
        mutations=[lambda r:r.update(status='unknown'),lambda r:r.update(model='other'),
            lambda r:r.update(service_tier='standard'),lambda r:r.update(input_tokens=True),
            lambda r:r.update(output_tokens=8193),lambda r:r.update(request_sha256='0'*64),
            lambda r:r.update(extra=1),lambda r:r.update(artifact={'tool':'explain_divergence','arguments':{}}),
            lambda r:r.update(artifact={'tool':'done','arguments':{'x':1}}),
            lambda r:r.update(status='OUTPUT_LIMIT')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                controller,ports=self.make();ports.query_mutation=mutation
                with self.assertRaises(c.Refused):controller.run()
                self.assertEqual(ports.graph_calls,[])
                self.assertEqual(ports.hidden_calls,[])

    def test_graph_failure_is_terminal_not_exhaustion(self):
        controller,ports=self.make();ports.graph_fault=ContractError('synthetic-canary')
        with self.assertRaises(ContractError):controller.run()
        self.assertNotIn('graph-planner-0-capsule',ports.records)
        self.assertEqual(ports.hidden_calls,[])

    def test_no_calls_after_close_or_phase_reuse(self):
        controller,ports=self.make();controller.run()
        count=len(ports.requests)
        with self.assertRaises(c.Refused):controller.role('planner','late')
        self.assertEqual(len(ports.requests),count)
        with self.assertRaisesRegex(c.Refused,'controller-reused'):controller.run()

    def test_binding_tamper_and_snapshot_mismatch_refuse_before_admission(self):
        for field,value in [('cap_microdollars',51000001),('window_seconds',26881),
            ('query_policy_sha256','0'*64),('graph_projection_sha256','0'*64),
            ('graph_inventory_sha256','0'*64),('graph_profile_sha256','0'*64),
            ('graph_authority_sha256','0'*64),('feedback_contract_sha256','0'*64)]:
            controller,ports=self.make();row=copy.deepcopy(controller.binding);row[field]=value
            with self.subTest(field=field),self.assertRaises(c.Refused):
                g.GraphController(ports,row,base.CONTEXT,controller.graph,ports.clock)
            self.assertEqual(ports.records,{})

    def test_graph_off_still_has_no_query_turns_or_capsule(self):
        ports=base.Ports((1,2,3,4,5,6))
        result=c.Controller(ports,base.binding(),base.CONTEXT,base.Clock()).run()
        self.assertEqual(result['reserved_microdollars'],37664000)
        self.assertTrue(all('graph_evidence' not in r for r in ports.requests))
        self.assertEqual(result['graph_mode'],'off')

    def test_ledger_write_fault_prevents_send(self):
        controller,ports=self.make()
        original=ports.record
        def fail(name,row):
            if name=='graph-planner-0-1-request':raise OSError('synthetic-write-fault')
            original(name,row)
        ports.record=fail
        with self.assertRaises(OSError):controller.run()
        self.assertEqual(ports.counts,[])
        self.assertEqual(ports.requests,[])

    def test_keyboard_interrupt_reraised_and_models_closed(self):
        controller,ports=self.make()
        def interrupt(*args):raise KeyboardInterrupt()
        ports.generate=interrupt
        with self.assertRaises(KeyboardInterrupt):controller.run()
        self.assertTrue(ports.closed)

    def test_query_deadline_no_extension(self):
        controller,ports=self.make()
        original=ports.generate
        def late(request,deadline):
            row=original(request,deadline);ports.clock.value=deadline;return row
        ports.generate=late
        with self.assertRaisesRegex(c.Refused,'deadline'):controller.run()
        self.assertEqual(ports.graph_calls,[])
        self.assertEqual(controller.end,controller.start+26880)

    def test_graph_local_deadline_enforced(self):
        controller,ports=self.make();original=ports.graph_call
        def late(session,role,phase,tool,arguments,deadline,cap):
            result=original(session,role,phase,tool,arguments,deadline,cap)
            ports.clock.value=deadline;return result
        ports.graph_call=late
        with self.assertRaisesRegex(c.Refused,'deadline'):controller.run()
        self.assertEqual(ports.hidden_calls,[])

    def test_bounded_g2_pagination_and_cap_restore(self):
        controller,_=self.make();session=controller.graph
        result=session.call('planner',0,'graph_node',
            dict(node_id='legacy:field:balance',include_source=True),result_cap=1024)
        self.assertLessEqual(len(c.canonical(result)),1024)
        self.assertEqual(session._tools.cap,7168)
        for cap in (True,1023,7169):
            with self.assertRaises(ContractError):
                session.call('planner',0,'graph_search',dict(query='BALANCE'),result_cap=cap)

    def test_canary_unreachable_in_query_transcript(self):
        controller,ports=self.make();controller.run()
        transcript=c.canonical(ports.records)
        self.assertNotIn(legacy.CANARY.encode(),transcript)
        self.assertNotIn(b'expected_output',transcript)
        self.assertTrue(any(k.endswith('-tool-response') for k in ports.records))

    def test_32_feedback_rows_include_streams_and_exit(self):
        rows=[dict(channel=channel,field=field,records_different=9999999999,
            records_compared=9999999999) for channel,fields in c.FIELDS.items() for field in fields]
        self.assertEqual(len(rows),32)
        feedback=adapter.envelope(base.H,base.H,'PUBLIC_DIVERGENCE',rows)
        self.assertEqual(len(feedback['divergences']),32)
        self.assertFalse(feedback['truncated'])
        c.validate_feedback(feedback,base.H,base.H,'PUBLIC_DIVERGENCE')
        self.assertEqual([r['channel'] for r in feedback['divergences'][-3:]],['stdout','stderr','exit'])

    def test_prefix_unicode_and_escape_bounds(self):
        for source in ('"'*1000,'\U0001f642'*1000,'\n'*1000):
            result=g.prefix(source,256)
            self.assertLessEqual(len(c.canonical(result['text'])),256)
            result['text'].encode('utf-8')
            self.assertTrue(result['truncated'])

    def test_capsule_selection_is_whole_responses_newest_first(self):
        a=dict(projection_sha256=base.H,items=['a'*3500])
        b=dict(projection_sha256=base.H,items=['b'*3500])
        d=dict(projection_sha256=base.H,items=['d'*3500])
        capsule=g.select_capsule(base.H,[a,b,d])
        self.assertEqual(capsule['responses'],[d])
        self.assertLessEqual(len(c.canonical(capsule)),8192)

    def test_query_instruction_capsule_guidance_and_policy_hash(self):
        for phrase in ('7,000 bytes', 'whole results', 'newest first',
                       'narrow questions', 'most important result last'):
            self.assertIn(phrase,g.INSTRUCTION)
        root=Path(__file__).resolve().parents[1]
        policy=json.loads((root/'spec/graph-repair-controller/2026-11-17-c-r1/QUERY-POLICY.json').read_bytes())
        self.assertEqual(policy['instructions'],g.INSTRUCTION)
        self.assertEqual(policy['query_policy_sha256'],g.QUERY_HASH)

    def test_budget_arithmetic_and_caps_exact(self):
        planner=sum(g.hold(g.input_cap('planner',0,n)) for n in range(1,9))
        initial=sum(g.hold(g.input_cap('builder',0,n)) for n in range(1,4))
        repair=sum(g.hold(g.input_cap('builder',1,n)) for n in range(1,4))
        self.assertEqual((planner,initial,repair),(4866048,1148928,1284096))
        self.assertEqual(c.MAX_RESERVATION+planner+initial+5*repair,g.MAX_RESERVATION)
        self.assertEqual(c.WINDOW+26*360,g.WINDOW)

    def test_component_projection_bounds_every_turn(self):
        source='"'*8190+'s'*(65536-8190)
        plan=analysis='"'*8191
        history=[dict(round=n,candidate='f'*16,match=4999999999,different=5000000000) for n in range(6)]
        rows=[dict(channel=channel,field=field,records_different=9999999999,
            records_compared=9999999999) for channel,fields in c.FIELDS.items() for field in fields]
        feedback=adapter.envelope(c.sha(source.encode()),'b'*64,'PUBLIC_DIVERGENCE',rows)
        previous=[]
        for turn in range(1,9):
            role,phase=('planner',0)
            row=g.query_projection(role,phase,turn,base.H,plan,source,analysis,history,None,previous,'b'*64)
            self.assertLessEqual(len(c.canonical(row))+4096,g.input_cap(role,phase,turn))
            if turn<=3:
                row=g.query_projection('builder',5,turn,base.H,plan,source,analysis,history,feedback,previous,'b'*64)
                self.assertLessEqual(len(c.canonical(row))+4096,g.input_cap('builder',5,turn))
            previous.append({'synthetic':'x'*(8192-len(c.canonical({'synthetic':''})))})

    def test_maximum_context_complete_artifact_projections(self):
        # The dedicated workflow downloads only this pinned public context file.
        # Full discovery also covers the same component limits without network.
        context={'x':'x'*(81920-8)}
        self._artifact_bounds(context)

    def _artifact_bounds(self,context):
        controller,_=self.make(context=context)
        controller.capsule={'synthetic':'x'*(8192-len(c.canonical({'synthetic':''})))}
        source='"'*8190+'s'*(65536-8190)
        plan=analysis='"'*8191
        history=[dict(round=n,candidate='f'*16,match=4999999999,different=5000000000) for n in range(6)]
        rows=[dict(channel=ch,field=f,records_different=9999999999,records_compared=9999999999)
              for ch,fields in c.FIELDS.items() for f in fields]
        feedback=adapter.envelope(c.sha(source.encode()),'b'*64,'PUBLIC_DIVERGENCE',rows)
        for role in c.CAPS:
            row=controller.project(role,context,plan,source,analysis,history,feedback)
            self.assertLessEqual(len(c.canonical(row))+4096,c.CAPS[role])
        return True


def pinned_context_proof(path):
    raw=Path(path).read_bytes()
    if c.sha(raw)!='4f25b42be20c5e4bb0a82030e3172b5c6751c7dfb5b36aa1f1bb42dee25a5a52':
        raise ValueError('context-hash')
    context=json.loads(raw)
    if 'LICENSE' in context or 'NOTICE' not in context or len(c.canonical(context))!=69808:
        raise ValueError('context-members')
    case=GraphRepairTests()
    try:case._artifact_bounds(context)
    finally:case.doCleanups()
    print('pinned-context-artifact-bounds-pass')
