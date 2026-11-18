"""Portable synthetic ports; no provider, Docker, oracle or hidden data."""
import copy
import json
import unittest
from lightyear_factory import public_repair_controller as c

H = 'a'*64
CONTEXT = {'public.cbl': 'PUBLIC SYNTHETIC SOURCE'}


def binding(context=None):
    return dict(schema='public-repair-binding/1', graph_mode='off', max_repairs=5,
        window_seconds=c.WINDOW, cap_microdollars=c.CEILING, model=c.MODEL,
        service_tier='flex', output_cap=32000, retries=0, authority_sha256=H,
        implementation_sha256=H, public_context_sha256=c.digest(CONTEXT if context is None else context),
        public_suite_sha256='b'*64, heldout_commitment_sha256='c'*64,
        runtime_profile_sha256='d'*64, feedback_contract_sha256=c.FEEDBACK_HASH, role_instructions_sha256=c.ROLE_HASH, public_case_count=16)


def feedback(source, suite='b'*64, kind='PUBLIC_DIVERGENCE'):
    return dict(schema='public-repair-feedback/1',candidate_sha256=c.sha(source.encode()),
        public_suite_sha256=suite,kind=kind,divergences=[],diagnostics=[],truncated=False)


class Clock:
    def __init__(self): self.value = 123456.789012345
    def __call__(self): return self.value


class Ports:
    def __init__(self, scores=(16,), compile_fail=()):
        self.scores = list(scores)
        self.compile_fail = set(compile_fail)
        self.records = {}
        self.requests = []
        self.counts = []
        self.hidden_calls = []
        self.closed = False
        self.fail = None
        self.builder_number = 0
        self.artifacts = {}

    def retain_artifact(self, slot, key, text):
        assert slot not in self.artifacts
        self.artifacts[slot] = (key, text)
        return c.sha(text.encode('utf-8'))

    def admit(self, raw, deadline):
        if self.fail == 'admit': raise c.Refused('binding-hash')
        return dict(binding_sha256=c.sha(raw), receipt_sha256=H)

    def record(self, name, row):
        if self.fail == 'record': raise OSError('synthetic ledger fault')
        if name in self.records: raise AssertionError('exclusive-record-collision')
        self.records[name] = copy.deepcopy(row)

    def count(self, request, deadline):
        assert not self.closed
        self.counts.append(copy.deepcopy(request))
        if self.fail == 'count': raise RuntimeError('synthetic uncertain send')
        return dict(input_tokens=100, request_sha256=c.digest(request), receipt_sha256=H)

    def generate(self, request, deadline):
        assert not self.closed
        self.requests.append(copy.deepcopy(request))
        if self.fail == 'generate': raise KeyboardInterrupt()
        if request['role'] in ('builder','repair'):
            self.builder_number += 1
            artifact = {'source':'public class Main { /* '+str(self.builder_number)+' */ }'}
        else: artifact = {'text':'public plan or analysis'}
        if self.fail == 'artifact': artifact = {'text':'bad\\x00'}
        return dict(artifact=artifact, input_tokens=101, output_tokens=500,
            model=c.MODEL, service_tier='flex', request_sha256=c.digest(request), receipt_sha256=H)

    def build(self, source, round, deadline):
        if self.fail == 'build': raise OSError('daemon synthetic fault')
        return dict(status='COMPILE_FAILED' if round in self.compile_fail else 'BUILT',
                    artifact_sha256=c.sha(source.encode()), build_receipt_sha256=H, cleanup=True,
                    feedback=feedback(source,kind='COMPILE_FAILED') if round in self.compile_fail else None)

    def evaluate_public(self, built, suite, deadline):
        if self.fail == 'public': raise OSError('public evaluator fault')
        match = self.scores.pop(0)
        return dict(suite_sha256=suite, artifact_sha256=built['artifact_sha256'],
            build_receipt_sha256=built['build_receipt_sha256'], match=match, different=16-match,
            total=16, complete=True, cleanup=True, receipt_sha256=H,
            feedback=dict(feedback('',suite),candidate_sha256=built['artifact_sha256']))

    def close_models(self):
        self.closed = True
        if self.fail == 'close': raise OSError('close failed')

    def evaluate_hidden(self, selected, commitment, deadline):
        assert self.closed
        self.hidden_calls.append(copy.deepcopy(selected))
        if self.fail == 'hidden': raise OSError('uncertain hidden call')
        return dict(status='PASS', receipt_sha256=H, cleanup=True)


class PublicRepairTests(unittest.TestCase):
    def make(self, ports=None, context=None):
        ports = Ports() if ports is None else ports
        context = CONTEXT if context is None else context
        return c.Controller(ports, binding(context), context, Clock()), ports

    def test_early_match_closes_models_and_hidden_once(self):
        controller, ports = self.make()
        result = controller.run()
        self.assertEqual(result['status'],'CANDIDATE_PASS')
        self.assertFalse(result['qualified'])
        self.assertEqual(len(ports.requests),2)
        self.assertEqual(len(ports.hidden_calls),1)
        self.assertTrue(ports.closed)
        self.assertEqual(result['reserved_microdollars'],4224000)

    def test_five_repairs_full_hold_and_public_fail(self):
        controller, ports = self.make(Ports((1,2,3,4,5,6)))
        result = controller.run()
        self.assertEqual(len(ports.requests),12)
        self.assertEqual(len(ports.counts),12)
        self.assertEqual(len(result['score_history']),6)
        self.assertEqual(result['reserved_microdollars'],37664000)
        self.assertEqual(result['status'],'PUBLIC_FAIL')
        self.assertEqual(result['selected']['round'],5)

    def test_best_public_score_ties_latest(self):
        controller, ports = self.make(Ports((5,9,8,9,2,3)))
        result = controller.run()
        self.assertEqual(result['selected']['round'],3)
        self.assertEqual(ports.hidden_calls,[])
        self.assertEqual(result['hidden'],dict(status='NOT_RUN',reason='public-fail'))
        self.assertEqual(result['selected']['artifact_sha256'],
                         ports.records['attempt-3']['artifact_sha256'])

    def test_last_compile_failure_uses_best_earlier(self):
        controller, ports = self.make(Ports((5,9,8,4,2),compile_fail=(5,)))
        result = controller.run()
        self.assertEqual(result['selected']['round'],1)
        self.assertIsNone(result['score_history'][-1]['match'])
        self.assertEqual(ports.hidden_calls,[])

    def test_all_compile_failures_skip_hidden(self):
        controller, ports = self.make(Ports((),compile_fail=range(6)))
        result = controller.run()
        self.assertIsNone(result['selected'])
        self.assertEqual(result['hidden'],dict(status='NOT_RUN',reason='no-evaluated-candidate'))
        self.assertEqual(result['status'],'CANDIDATE_FAIL')
        self.assertEqual(ports.hidden_calls,[])

    def test_compile_failure_initial_can_repair(self):
        controller, ports = self.make(Ports((16,),compile_fail=(0,)))
        result = controller.run()
        self.assertEqual(result['selected']['round'],1)
        self.assertEqual(len(ports.requests),4)

    def test_best_source_not_latest_inferior_source_in_projection(self):
        controller, ports = self.make(Ports((7,2,16)))
        controller.run()
        analyses = [x for x in ports.requests if x['role']=='analysis']
        self.assertEqual(analyses[0]['source'],analyses[1]['source'])
        self.assertEqual(len(analyses[1]['score_history']),2)
        self.assertEqual(analyses[1]['feedback']['candidate_sha256'],c.sha(analyses[1]['source'].encode()))
        self.assertNotIn('hidden',analyses[1])

    def test_history_is_bounded_and_contains_all_produced_candidates(self):
        controller, ports = self.make(Ports((1,2,3,4,5,6)))
        controller.run()
        request = ports.requests[-1]
        self.assertEqual(len(request['score_history']),5)
        self.assertLessEqual(len(c.canonical({'score_history':request['score_history']})),1024)
        self.assertEqual(set(request['score_history'][0]),{'round','candidate','match','different'})

    def test_no_calls_after_hidden_or_controller_reuse(self):
        controller, ports = self.make()
        controller.run()
        with self.assertRaisesRegex(c.Refused,'controller-reused'): controller.run()
        with self.assertRaisesRegex(c.Refused,'model-closed'): controller.role('planner','late')
        self.assertEqual(len(ports.hidden_calls),1)

    def test_uncertain_count_no_generation_or_retry(self):
        controller, ports = self.make(); ports.fail='count'
        with self.assertRaises(RuntimeError): controller.run()
        self.assertEqual(len(ports.counts),1)
        self.assertEqual(ports.requests,[])
        self.assertEqual(controller.reserved,c.HOLDS['planner'])
        self.assertEqual(ports.records['planner-failed']['refusal_code'],'port-fault')
        self.assertEqual(ports.hidden_calls,[])

    def test_interrupt_is_not_reinterpreted(self):
        controller, ports = self.make(); ports.fail='generate'
        with self.assertRaises(KeyboardInterrupt): controller.run()
        self.assertIn('planner-failed',ports.records)
        self.assertTrue(ports.closed)

    def test_build_public_and_close_faults_never_fallback_to_hidden(self):
        for fault in ('build','public','close'):
            controller, ports = self.make(); ports.fail=fault
            with self.subTest(fault=fault), self.assertRaises(OSError): controller.run()
            self.assertEqual(ports.hidden_calls,[])
            self.assertIn('stopped',ports.records)

    def test_uncertain_hidden_consumes_once_and_no_followup_send(self):
        controller, ports = self.make(); ports.fail='hidden'
        with self.assertRaises(OSError): controller.run()
        self.assertIn('hidden-invocation',ports.records)
        self.assertEqual(len(ports.hidden_calls),1)
        self.assertEqual(len(ports.requests),2)
        self.assertTrue(ports.closed)

    def test_admission_failure_never_calls_provider(self):
        controller, ports = self.make(); ports.fail='admit'
        with self.assertRaises(c.Refused): controller.run()
        self.assertEqual(ports.records,{})
        self.assertEqual(ports.counts,[])

    def test_durable_reservation_failure_prevents_count(self):
        controller, ports = self.make(); ports.fail='record'
        with self.assertRaises(OSError): controller.run()
        self.assertEqual(ports.counts,[])
        self.assertTrue(ports.closed)

    def test_actual_count_and_usage_may_differ(self):
        controller, ports = self.make()
        controller.run()
        row=ports.records['planner-complete']
        self.assertEqual(row['counted_input_tokens'],100)
        self.assertEqual(row['usage_input_tokens'],101)
        self.assertFalse(row['count_usage_match'])
        self.assertEqual(row['accounted_microdollars'],13481)

    def test_provider_identity_or_usage_tamper_stops(self):
        for field,value,code in (('service_tier','default','generation-response'),
                                ('model','other','generation-response'),
                                ('output_tokens',32001,'usage-bound'),
                                ('input_tokens',True,'usage-bound')):
            controller, ports = self.make()
            original=ports.generate
            def changed(request,deadline):
                row=original(request,deadline);row[field]=value;return row
            ports.generate=changed
            with self.subTest(field=field), self.assertRaisesRegex(c.Refused,code): controller.run()
            self.assertEqual(ports.hidden_calls,[])

    def test_artifact_caps_c0_and_exact_keys(self):
        for artifact,code in (({'text':'x'*8193},'artifact-cap'),
                              ({'text':'bad\x00'},'artifact-text'),
                              ({'text':'okay','unexpected':1},'artifact-shape')):
            controller, ports=self.make();original=ports.generate
            def changed(request,deadline):
                row=original(request,deadline);row['artifact']=artifact;return row
            ports.generate=changed
            with self.subTest(code=code), self.assertRaisesRegex(c.Refused,code):controller.run()
            self.assertEqual(ports.records['planner-failed']['refusal_code'],code)

    def test_encoded_expansion_refuses_before_next_role_reservation(self):
        controller, ports=self.make();original=ports.generate
        def changed(request,deadline):
            row=original(request,deadline);row['artifact']={'text':'\t'*8192};return row
        ports.generate=changed
        with self.assertRaisesRegex(c.Refused,'component-cap'):controller.run()
        self.assertNotIn('builder-0-reservation',ports.records)

    def test_projection_bound_refuses_without_sending(self):
        controller, ports=self.make()
        controller.context={'huge':'x'*112000}
        with self.assertRaisesRegex(c.Refused,'context-cap'):controller.run()
        self.assertEqual(ports.counts,[])
        self.assertEqual(controller.reserved,0)

    def test_all_four_worst_component_projections_fit_fixed_caps(self):
        context={'x':'a'*(98304-8)}
        plan='"'*8191
        source='"'*8190+'a'*(65536-8190)
        analysis='"'*8191
        history=[dict(round=n,candidate='f'*16,match=9999999999,different=0) for n in range(6)]
        self.assertEqual(len(c.canonical(context)),98304)
        self.assertEqual(len(c.canonical(plan)),16384)
        self.assertEqual(len(c.canonical(source)),73728)
        for role in c.CAPS:
            request=c.projection(role,context,plan,source,analysis,history,feedback(source))
            self.assertLessEqual(len(c.canonical(request))+4096,c.CAPS[role])

    def test_original_deadline_cannot_extend(self):
        controller, ports=self.make()
        original=ports.count
        def late(request,deadline):
            row=original(request,deadline);controller.clock.value=deadline;return row
        ports.count=late
        with self.assertRaisesRegex(c.Refused,'deadline'):controller.run()
        self.assertEqual(ports.requests,[])
        self.assertEqual(controller.end,controller.start+c.WINDOW)

    def test_binding_rejects_graph_enablement_cap_and_window_changes(self):
        for field,value in (('graph_mode','on'),('window_seconds',26880),
                            ('cap_microdollars',50000000),('max_repairs',6),
                            ('role_instructions_sha256','0'*64),('retries',1)):
            row=binding();row[field]=value
            with self.subTest(field=field), self.assertRaises(c.Refused):
                c.Controller(Ports(),row,CONTEXT)

    def test_mutating_caller_binding_or_context_does_not_rebind(self):
        row=binding(); context=dict(CONTEXT)
        controller=c.Controller(Ports(),row,context,Clock())
        row['cap_microdollars']=1;context['secret']='NOT_DISCLOSED'
        controller.run()
        self.assertNotIn('secret',controller.context)
        self.assertEqual(controller.binding['cap_microdollars'],c.CEILING)

    def test_public_join_incomplete_score_and_cleanup_refuse(self):
        for key,value in (('suite_sha256','0'*64),('artifact_sha256','0'*64),
                          ('complete',False),('cleanup',False),('match',17),('total',True)):
            controller,ports=self.make();original=ports.evaluate_public
            def changed(*args):
                row=original(*args);row[key]=value;return row
            ports.evaluate_public=changed
            with self.subTest(key=key),self.assertRaisesRegex(c.Refused,'public-response'):controller.run()
            self.assertEqual(ports.hidden_calls,[])

    def test_no_hidden_content_in_model_requests(self):
        controller,ports=self.make(Ports((2,16)))
        original=ports.evaluate_hidden
        def hidden(*args):
            result=original(*args);result['receipt_sha256']='f'*64;return result
        ports.evaluate_hidden=hidden
        controller.run()
        encoded=c.canonical(ports.requests)
        self.assertNotIn(('f'*64).encode(),encoded)
        self.assertNotIn(b'heldout',encoded)
        self.assertTrue(ports.closed)

    def test_port_fault_code_never_exposes_exception_text(self):
        controller,ports=self.make();ports.fail='build'
        with self.assertRaises(OSError):controller.run()
        self.assertEqual(ports.records['stopped']['refusal_code'],'port-fault')
        self.assertNotIn('daemon',json.dumps(ports.records))

    def test_canonical_rejects_floats(self):
        for value in (0.1,float('nan'),float('inf'),{'x':1.0}):
            with self.assertRaises(c.Refused):c.canonical(value)

    def test_artifact_readback_mismatch_stops_before_build(self):
        controller,ports=self.make()
        ports.retain_artifact=lambda *args:'0'*64
        with self.assertRaisesRegex(c.Refused,'artifact-retention'):controller.run()
        self.assertEqual(ports.hidden_calls,[])
        self.assertNotIn('attempt-0',ports.records)

    def test_phase_deadlines_passed_to_ports(self):
        controller,ports=self.make()
        deadlines=[];original=ports.generate
        def timed(request,deadline):
            deadlines.append(deadline-controller.clock());return original(request,deadline)
        ports.generate=timed
        controller.run()
        self.assertEqual(deadlines,[900,900])

    def test_hidden_fail_after_public_match_is_candidate_fail(self):
        controller,ports=self.make()
        ports.evaluate_hidden=lambda selected,commitment,deadline:dict(status='FAIL',receipt_sha256=H,cleanup=True)
        self.assertEqual(controller.run()['status'],'CANDIDATE_FAIL')


class FeedbackTests(unittest.TestCase):
    def validate(self,row):
        return c.validate_feedback(row,c.sha(b'source'),'b'*64,row.get('kind'))

    def test_b2_public_failure_never_invokes_hidden(self):
        p=Ports((1,2,3,4,5,6));run=c.Controller(p,binding(),CONTEXT,Clock())
        result=run.run()
        self.assertEqual(result['status'],'PUBLIC_FAIL')
        self.assertEqual(result['hidden'],{'status':'NOT_RUN','reason':'public-fail'})
        self.assertNotIn('hidden-invocation',p.records)
        self.assertEqual(p.hidden_calls,[])
        self.assertTrue(p.closed)

    def test_exact_current_source_feedback_reaches_analysis_and_repair(self):
        p=Ports((7,2,16));c.Controller(p,binding(),CONTEXT,Clock()).run()
        requests=[r for r in p.requests if r['role'] in ('analysis','repair')]
        self.assertEqual(len(requests),4)
        for r in requests:
            self.assertEqual(r['feedback']['candidate_sha256'],c.sha(r['source'].encode()))
            self.assertEqual(r['feedback'],p.records['public-feedback-0'])
            self.assertNotIn('feedback_history',r)
        for r in p.requests[:2]:self.assertNotIn('feedback',r)

    def test_compile_diagnostic_is_joined_when_no_best_exists(self):
        p=Ports((16,),compile_fail=(0,));original=p.build
        def build(*args):
            r=original(*args)
            if r['feedback'] is not None:r['feedback']['diagnostics']=[dict(line=4,column=2,message='cannot find symbol')]
            return r
        p.build=build;c.Controller(p,binding(),CONTEXT,Clock()).run()
        f=p.requests[2]['feedback']
        self.assertEqual(f['kind'],'COMPILE_FAILED')
        self.assertEqual(f['diagnostics'][0]['line'],4)

    def test_shape_and_mutually_exclusive_payloads(self):
        for key,value in [('extra','CASE_CONTENT'),('schema','other'),('truncated',1),('kind','HIDDEN')]:
            r=feedback('source');r[key]=value
            with self.subTest(key=key),self.assertRaises(c.Refused):self.validate(r)
        r=feedback('source');r['diagnostics']=[dict(line=1,column=1,message='x')]
        with self.assertRaisesRegex(c.Refused,'feedback-shape'):self.validate(r)

    def test_candidate_and_suite_join_refuse(self):
        for key in ('candidate_sha256','public_suite_sha256'):
            r=feedback('source');r[key]='e'*64
            with self.subTest(key=key),self.assertRaisesRegex(c.Refused,'feedback-join'):self.validate(r)

    def test_closed_field_channel_and_integer_counts(self):
        good=dict(channel='ACCTFILE',field='ACCT-CURR-BAL',records_different=1,records_compared=2)
        for key,value in [('channel','hidden'),('field','VALUE=123'),('records_different',True),('records_compared',1.5),('records_different',3)]:
            r=feedback('source');r['divergences']=[dict(good,**{key:value})]
            with self.subTest(key=key,value=value),self.assertRaises(c.Refused):self.validate(r)
        r=feedback('source');r['divergences']=[good]
        self.assertEqual(self.validate(r)['divergences'],[good])

    def test_divergence_order_and_duplicates_refuse(self):
        a=dict(channel='ACCTFILE',field='',records_different=0,records_compared=1)
        b=dict(channel='exit',field='',records_different=0,records_compared=1)
        for rows in ([b,a],[a,a]):
            r=feedback('source');r['divergences']=rows
            with self.assertRaisesRegex(c.Refused,'feedback-row'):self.validate(r)

    def test_row_and_diagnostic_count_caps(self):
        r=feedback('source');r['divergences']=[{}]*33
        with self.assertRaisesRegex(c.Refused,'feedback-cap'):self.validate(r)
        r=feedback('source',kind='COMPILE_FAILED');r['diagnostics']=[{}]*5
        with self.assertRaisesRegex(c.Refused,'feedback-cap'):self.validate(r)

    def test_diagnostic_integer_control_and_encoded_message_caps(self):
        for key,value in [('line',True),('column',-1),('message','x\x00'),('message','x'*511)]:
            r=feedback('source',kind='COMPILE_FAILED')
            r['diagnostics']=[dict(dict(line=1,column=2,message='safe'),**{key:value})]
            with self.subTest(key=key),self.assertRaisesRegex(c.Refused,'feedback-diagnostic'):self.validate(r)

    def test_canonical_envelope_byte_cap(self):
        r=feedback('source');r['divergences']=[dict(channel='ACCTFILE',field='ACCT-CURR-BAL',records_different=0,records_compared=1)]
        r['diagnostics']=[dict(line=1,column=2,message='x'*4096)]
        with self.assertRaisesRegex(c.Refused,'feedback-cap'):self.validate(r)

    def test_feedback_snapshot_not_caller_mutable(self):
        r=feedback('source');v=self.validate(r);r['truncated']=True
        self.assertFalse(v['truncated'])

    def test_invalid_port_feedback_stops_before_repair_send(self):
        p=Ports((1,));original=p.evaluate_public
        def evaluate(*args):
            r=original(*args);r['feedback']['candidate_sha256']='e'*64;return r
        p.evaluate_public=evaluate
        with self.assertRaisesRegex(c.Refused,'feedback-join'):c.Controller(p,binding(),CONTEXT,Clock()).run()
        self.assertEqual(len(p.requests),2)
        self.assertEqual(p.hidden_calls,[])

    def test_feedback_policy_hash_is_admitted(self):
        b=binding();b['feedback_contract_sha256']='0'*64
        with self.assertRaisesRegex(c.Refused,'binding-hash'):c.Controller(Ports(),b,CONTEXT)

    def test_slash_literals_are_not_a_controller_path_filter(self):
        for message in ('String p = dir + "/" + name;',"char c = '/';",'a/b; // ratio','</b>'):
            r=feedback('source',kind='COMPILE_FAILED');r['diagnostics']=[dict(line=1,column=1,message=message)]
            self.assertEqual(self.validate(r)['diagnostics'][0]['message'],message)


if __name__=='__main__': unittest.main()
