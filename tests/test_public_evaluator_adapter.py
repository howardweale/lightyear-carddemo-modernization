"""Synthetic workers only; no Docker/compiler/provider execution."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from lightyear_factory import public_evaluator_adapter as a

ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/'tests/fixtures/reference-execution/public-cases'
H='a'*64


class Worker:
    def __init__(self,cases):self.cases=iter(cases);self.exit=0;self.stderr=b'';self.tamper={};self.observed_inputs=[];self.limits=[]
    def compile(self,source,round_no,deadline):
        row=dict(phase='javac',exit_code=self.exit,stderr=self.stderr,artifact_sha256=a.sha(source.encode()),
            receipt_sha256=H,cleanup=True,daemon_ok=True,image_match=True,tool_hash_match=True,
            timed_out=False,diagnostic_mode='javac-XDrawDiagnostics')
        row.update(self.tamper);return row
    def run_public(self,built,inputs,timestamp,date,deadline,limits):
        self.limits.append(limits)
        self.observed_inputs.append(inputs)
        case=next(self.cases)
        row={k:case['expected'].get(k,b'') for k in a.CHANNELS}
        row.update(timed_out=False,output_capped=False,cleanup=True,receipt_sha256=H,artifact_sha256=built['artifact_sha256'],
                   build_receipt_sha256=built['build_receipt_sha256'])
        row.update(self.tamper);return row


class PublicAdapterTests(unittest.TestCase):
    def adapter(self):
        raw=(SUITE/'SUITE.json').read_bytes();cases=a.public_suite(raw,SUITE)
        worker=Worker(cases);adapter=a.PublicAdapter(worker,raw,SUITE,ROOT,a.sha,clock=lambda:0)
        return adapter,worker

    def test_fractional_clock_keeps_both_worker_intervals_inside_the_caps(self):
        cleanup_boundary = 1_006_000_000_027 / 1_000_000_000
        execution_boundary = 1_010_000_000_027 / 1_000_000_000
        self.assertGreater((cleanup_boundary + 20) - (cleanup_boundary + 15), 5)
        self.assertGreater((execution_boundary + 15) - execution_boundary, 15)
        for now in (cleanup_boundary, execution_boundary):
            with self.subTest(now=now):
                adapter, worker = self.adapter()
                adapter.clock = lambda: now
                phase_end = now + 600
                built = adapter.build('class Main {}', 0, phase_end)
                adapter.evaluate_public(built, a.PUBLIC_SUITE, phase_end)
                self.assertEqual(len(worker.limits), 16)
                for limits in worker.limits:
                    execution = limits['execution_deadline']
                    cleanup = limits['cleanup_deadline']
                    self.assertGreater(execution, now)
                    self.assertLessEqual(execution - now, 15)
                    self.assertGreater(cleanup, execution)
                    self.assertLessEqual(cleanup - execution, 5)
                    self.assertLessEqual(cleanup, phase_end)

    def test_phase_clip_and_exact_boundaries(self):
        self.assertEqual(a.case_deadlines(10., 100.), (25., 30.))
        self.assertEqual(a.case_deadlines(10., 21.), (16., 21.))
        with self.assertRaisesRegex(a.Refused, '^deadline$'):
            a.case_deadlines(10., 15.)

    def test_delivered_public_suite_hash_and_all_matches(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,10)
        result=adapter.evaluate_public(built,a.PUBLIC_SUITE,10)
        self.assertEqual((result['match'],result['different'],result['total']),(16,0,16))
        self.assertLessEqual(len(a.canonical(result['feedback'])),4096)
        self.assertTrue(all(set(i)=={'ACCTFILE','TCATBALF','DISCGRP','XREFFILE'} for i in w.observed_inputs))

    def test_changed_or_nonpublic_suite_refuses(self):
        with self.assertRaisesRegex(a.Refused,'public-suite-hash'):a.public_suite(b'{}',SUITE)

    def test_only_javac_one_is_compile_failure(self):
        adapter,w=self.adapter();w.exit=1;w.stderr=b'Main.java:4:2: compiler.err.cant.resolve: symbol\n1 error\n'
        r=adapter.build('bad source',0,10)
        self.assertEqual(r['status'],'COMPILE_FAILED')
        self.assertEqual(r['feedback']['diagnostics'][0]['line'],4)
        for code in (2,3,4,137,-9,True):
            w.exit=code
            with self.subTest(code=code),self.assertRaises(a.Refused):adapter.build('bad source',0,10)

    def test_infrastructure_faults_never_compile_feedback(self):
        adapter,w=self.adapter();w.exit=1
        for key,value in [('phase','docker'),('cleanup',False),('daemon_ok',False),('image_match',False),('tool_hash_match',False),('timed_out',True)]:
            w.tamper={key:value}
            with self.subTest(key=key),self.assertRaisesRegex(a.Refused,'build-infrastructure'):adapter.build('bad',0,10)

    def test_slash_literals_and_markup_preserved_without_refusal(self):
        for text in ('String p = dir + "/" + name;',"char c = '/';",'a/b; // ratio','</b>'):
            rows,_=a.compiler_rows(('Main.java:1:2: '+text+'\n').encode())
            self.assertEqual(rows[0]['message'],text)

    def test_private_paths_and_uri_arguments_redacted(self):
        for text in ('cannot read /private/build/x',r'cannot read X:\private\build\x','cannot read file:///private/x','cannot read https://example.invalid/private'):
            rows,_=a.compiler_rows(('Main.java:1:2: '+text+'\n').encode())
            self.assertNotIn('private',rows[0]['message'])
            self.assertIn('[path]',rows[0]['message'])

    def test_source_snippets_and_unknown_files_not_forwarded(self):
        rows,truncated=a.compiler_rows(b'Other.java:3:1: private sentinel\n  secret source line\n ^\n')
        self.assertTrue(truncated)
        self.assertEqual(rows,[dict(line=0,column=0,message='compiler-diagnostic-unavailable')])

    def test_diagnostic_bounds_order_and_c0(self):
        raw=b''.join(('Main.java:'+str(i)+':1: '+('x'*1000)+'\x00\n').encode() for i in range(8,0,-1))
        rows,truncated=a.compiler_rows(raw)
        self.assertTrue(truncated);self.assertEqual(len(rows),4)
        self.assertEqual([r['line'] for r in rows],[1,2,3,4])
        self.assertTrue(all(len(a.canonical(r['message']))<=512 and '\x00' not in r['message'] for r in rows))

    def test_whole_row_truncation(self):
        rows=[dict(channel='ACCTFILE',field='X'*500,records_different=1,records_compared=2) for _ in range(30)]
        result=a.envelope(H,H,'PUBLIC_DIVERGENCE',rows)
        self.assertTrue(result['truncated']);self.assertLessEqual(len(a.canonical(result)),4096)
        self.assertTrue(all(r in rows for r in result['divergences']))

    def test_field_counts_missing_record_and_filler_group(self):
        layout=SimpleNamespace(record_length=4,variable=False,overlays=(),fields=[
            SimpleNamespace(path='R.VALUE',offset=0,length=2),
            SimpleNamespace(path='R.FILLER',offset=2,length=1),
            SimpleNamespace(path='R.X.FILLER',offset=3,length=1)])
        expected=dict(ACCTFILE=b'abcdwxyz',TRANSACT=b'',stdout=b'ok\n',stderr=b'',exit=0)
        actual=dict(expected,ACCTFILE=b'abce')
        count,rows=a.tally([(expected,actual,True)],dict(ACCTFILE=layout,TRANSACT=layout))
        self.assertEqual(count,0)
        value=next(r for r in rows if r['channel']=='ACCTFILE' and r['field']=='VALUE')
        filler=next(r for r in rows if r['channel']=='ACCTFILE' and r['field']=='FILLER')
        self.assertEqual((value['records_different'],value['records_compared']),(1,2))
        self.assertEqual((filler['records_different'],filler['records_compared']),(2,2))

    def test_abend_case_ignores_files_but_compares_other_channels(self):
        expected=dict(stdout=b'ABEND\n',stderr=b'',exit=12)
        actual=dict(expected,ACCTFILE=b'ANY',TRANSACT=b'ANY')
        matches,rows=a.tally([(expected,actual,False)],{})
        self.assertEqual(matches,1)
        self.assertEqual(rows,[])

    def test_only_nonzero_divergences_consume_envelope_rows(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,10);w.tamper={'exit':91}
        result=adapter.evaluate_public(built,a.PUBLIC_SUITE,10)
        self.assertEqual([r['channel'] for r in result['feedback']['divergences']],['exit'])

    def test_lines_split_only_lf_not_formfeed(self):
        self.assertEqual(a.lines(b'a\x0cb\n'),[b'a\x0cb'])
        self.assertEqual(a.lines(b'a\nb'),[b'a',b'b'])

    def test_incomplete_cleanup_and_join_refuse(self):
        for key,value in [('cleanup',False),('artifact_sha256','f'*64),('exit',True)]:
            adapter,w=self.adapter();built=adapter.build('class Main {}',0,10);w.tamper={key:value}
            with self.subTest(key=key),self.assertRaisesRegex(a.Refused,'public-response'):adapter.evaluate_public(built,a.PUBLIC_SUITE,10)

    def test_receipt_readback_and_deadline_refuse(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,10);adapter.retain=lambda raw:'0'*64
        with self.assertRaisesRegex(a.Refused,'public-receipt-readback'):adapter.evaluate_public(built,a.PUBLIC_SUITE,10)
        with self.assertRaisesRegex(a.Refused,'deadline'):adapter.build('class Main {}',0,0)

    def test_feedback_contains_counts_not_output_values(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,10);w.tamper={'stdout':b'UNIQUE_PUBLIC_OUTPUT_SENTINEL'}
        result=adapter.evaluate_public(built,a.PUBLIC_SUITE,10)
        self.assertNotIn(b'UNIQUE_PUBLIC_OUTPUT_SENTINEL',a.canonical(result['feedback']))
        self.assertNotIn('case',a.canonical(result['feedback']).decode())



    def test_timeout_and_cap_are_differences_even_if_prefix_matches(self):
        for flag in ('timed_out','output_capped'):
            adapter,w=self.adapter();built=adapter.build('class Main {}',0,600);w.tamper={flag:True}
            result=adapter.evaluate_public(built,a.PUBLIC_SUITE,600)
            self.assertEqual((result['match'],result['different']),(0,16))
            rows=result['feedback']['divergences']
            self.assertEqual(next(r for r in rows if r['channel']=='exit')['records_different'],16)
            self.assertEqual(next(r for r in rows if r['channel']=='ACCTFILE' and r['field']=='')['records_different'],13)
            self.assertTrue(result['cleanup'])

    def test_limits_and_flags_are_retained_without_output_content(self):
        adapter,w=self.adapter();saved=[];adapter.retain=lambda raw:(saved.append(raw) or a.sha(raw))
        built=adapter.build('class Main {}',0,600);w.tamper={'timed_out':True}
        adapter.evaluate_public(built,a.PUBLIC_SUITE,600)
        self.assertEqual(len(w.limits),16)
        self.assertTrue(all(x==dict(execution_deadline=15,cleanup_deadline=20,output_bytes=8388608) for x in w.limits))
        receipt=a.json.loads(saved[0])
        self.assertTrue(all(x['timed_out'] and not x['output_capped'] for x in receipt['observations']))

    def test_sixteen_full_case_slots_fit_phase_with_cleanup(self):
        adapter,w=self.adapter();now=[0];adapter.clock=lambda:now[0];real=w.run_public
        def run(*args):
            row=real(*args);now[0]=args[-1]['cleanup_deadline'];row['timed_out']=True;return row
        w.run_public=run;built=adapter.build('class Main {}',0,600)
        r=adapter.evaluate_public(built,a.PUBLIC_SUITE,600)
        self.assertEqual(now[0],320);self.assertEqual((r['match'],r['different']),(0,16))

    def test_cleanup_fault_is_terminal_despite_candidate_limit(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,600)
        w.tamper={'timed_out':True,'cleanup':False}
        with self.assertRaisesRegex(a.Refused,'public-response'):adapter.evaluate_public(built,a.PUBLIC_SUITE,600)

    def test_limit_flags_are_booleans_not_integers(self):
        for flag in ('timed_out','output_capped'):
            adapter,w=self.adapter();built=adapter.build('class Main {}',0,600);w.tamper={flag:1}
            with self.subTest(flag=flag),self.assertRaisesRegex(a.Refused,'public-response'):adapter.evaluate_public(built,a.PUBLIC_SUITE,600)

    def test_worker_exception_remains_terminal(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,600)
        def broken(*args):raise RuntimeError('synthetic daemon failure')
        w.run_public=broken
        with self.assertRaises(RuntimeError):adapter.evaluate_public(built,a.PUBLIC_SUITE,600)

    def test_late_worker_is_not_a_candidate_timeout(self):
        adapter,w=self.adapter();now=[0];adapter.clock=lambda:now[0];real=w.run_public
        def late(*args):
            row=real(*args);now[0]=args[-1]['cleanup_deadline']+1;return row
        w.run_public=late;built=adapter.build('class Main {}',0,600)
        with self.assertRaisesRegex(a.Refused,'public-worker-deadline'):adapter.evaluate_public(built,a.PUBLIC_SUITE,600)

    def test_oversized_worker_payload_is_a_contract_fault(self):
        adapter,w=self.adapter();built=adapter.build('class Main {}',0,600)
        w.tamper={'output_capped':True,'stdout':b'x'*(a.OUTPUT_BYTES+1)}
        with self.assertRaisesRegex(a.Refused,'public-worker-output-contract'):adapter.evaluate_public(built,a.PUBLIC_SUITE,600)


    def test_all_timeouts_fit_original_phase_after_build_time(self):
        adapter,w=self.adapter();now=[0];adapter.clock=lambda:now[0]
        compile_worker=w.compile;run_worker=w.run_public
        def compile_with_elapsed(*args):
            result=compile_worker(*args);now[0]+=200;return result
        def timeout_with_cleanup(*args):
            result=run_worker(*args);now[0]=args[-1]['cleanup_deadline']
            result['timed_out']=True;return result
        w.compile=compile_with_elapsed;w.run_public=timeout_with_cleanup
        built=adapter.build('class Main {}',0,600)
        result=adapter.evaluate_public(built,a.PUBLIC_SUITE,600)
        self.assertEqual(now[0],520)
        self.assertLess(now[0],600)
        self.assertEqual((result['match'],result['different'],result['total']),(0,16,16))
        self.assertTrue(result['complete'] and result['cleanup'])
        self.assertEqual(len(w.limits),16)
        self.assertTrue(all(x['cleanup_deadline']-x['execution_deadline']==5 for x in w.limits))

if __name__=='__main__':unittest.main()
