import unittest
from unittest.mock import patch
try:
    import yaml
except ImportError:
    raise unittest.SkipTest('Required CI installs pinned PyYAML; optional in general suites')
from tools.ci_gate import selected,evaluate,expected_workflows,latest_runs,TerminalStability,current_files
class GateTests(unittest.TestCase):
    def test_docs_skip_heavy_but_json_does_not(self):
        e=expected_workflows(['docs/factory/review.md'])
        self.assertNotIn('.github/workflows/verify.yml',e)
        self.assertNotIn('.github/workflows/control-tower-decisions.yml',e)
        self.assertIn('.github/workflows/verify.yml',expected_workflows(['docs/receipt.json']))
    def test_shared_inputs_trigger_both(self):
        for p in ['src/lightyear_mainframe/records.py','src/lightyear_mainframe/zos_bindings.py','tests/mainframe/fixtures/x','spec/mainframe/x','tools/check_legacy_twin.py']:
            for w in ['factory-legacy-twin','factory-reconciliation']:
                self.assertIn(f'.github/workflows/{w}.yml',expected_workflows([p]),p)
    def test_only_final_head_completed_success_passes(self):
        r=dict(id=1,path='x',head_sha='new',event='pull_request',pull_requests=[{'number':9}],status='completed',conclusion='success')
        self.assertEqual(evaluate({'x'},[r],'new',9),([],[]))
        for c in ['failure','cancelled','skipped','neutral','timed_out']:
            self.assertEqual(evaluate({'x'},[dict(r,conclusion=c)],'new',9),(['x'],[]))
        for change in [{'head_sha':'old'},{'status':'in_progress'},{'pull_requests':[{'number':8}]}]:
            self.assertEqual(evaluate({'x'},[dict(r,**change)],'new',9),([],['x']))
        self.assertEqual(evaluate({'x'},[],'new',9),([],['x']))
        self.assertEqual(evaluate({'x'},[r,dict(r,id=2,conclusion='failure')],'new',9),(['x'],[]))
    def run_row(self, **changes):
        return dict(dict(id=10,path='x',head_sha='h',event='pull_request',pull_requests=[{'number':1}],
                         status='completed',conclusion='failure',run_attempt=1),**changes)

    def test_one_run_reports_only_its_latest_attempt(self):
        failed=self.run_row()
        rerunning=self.run_row(status='in_progress',conclusion=None,run_attempt=2)
        # Each API snapshot contains one row for this run ID, not both attempts.
        self.assertEqual((['x'],[]),evaluate({'x'},[failed],'h',1))
        self.assertEqual(([],['x']),evaluate({'x'},[rerunning],'h',1))
        success=self.run_row(conclusion='success',run_attempt=2)
        self.assertEqual(([],[]),evaluate({'x'},[success],'h',1))

    def test_rerun_not_yet_registered_does_not_end_gate_immediately(self):
        stable=TerminalStability(seconds=60)
        failed=self.run_row()
        snapshots=[(0,failed,False),(30,failed,False),
                   (45,self.run_row(run_attempt=2,status='queued',conclusion=None),False),
                   (60,self.run_row(run_attempt=2,conclusion='success'),False),
                   (119,self.run_row(run_attempt=2,conclusion='success'),False),
                   (120,self.run_row(run_attempt=2,conclusion='success'),True)]
        for now,row,ready in snapshots:
            chosen=latest_runs({'x'},[row],'h',1)
            _,waiting=evaluate({'x'},[row],'h',1)
            self.assertEqual(ready,stable.ready(chosen,waiting,now))

    def test_previous_success_cannot_hide_new_attempt_or_run(self):
        stable=TerminalStability(seconds=60)
        green=self.run_row(conclusion='success')
        self.assertFalse(stable.ready({'x':green},[],0))
        pending=self.run_row(run_attempt=2,status='queued',conclusion=None)
        self.assertFalse(stable.ready({'x':pending},['x'],60))
        failed=self.run_row(run_attempt=2)
        self.assertFalse(stable.ready({'x':failed},[],90))
        self.assertTrue(stable.ready({'x':failed},[],150))
        replacement=self.run_row(id=11,conclusion='success')
        self.assertEqual({'x':replacement},latest_runs({'x'},[failed,replacement],'h',1))
        self.assertFalse(stable.ready({'x':replacement},[],150))

    def test_current_files_uses_consistent_live_count_and_refuses_changed_base(self):
        pr=dict(head={'sha':'h'},base={'sha':'b','ref':'base'},changed_files=1)
        with patch('tools.ci_gate.api',side_effect=[pr,pr]),patch('tools.ci_gate.pages',return_value=[{'filename':'x.py'}]):
            files,identity=current_files('repos/fixture',1,'h')
        self.assertEqual(['x.py'],files)
        self.assertEqual(('h','b','base',1),identity)
        for changed in (dict(pr,base={'sha':'c','ref':'base'}),dict(pr,head={'sha':'new'}),dict(pr,changed_files=2)):
            with patch('tools.ci_gate.api',side_effect=[pr,changed]),patch('tools.ci_gate.pages',return_value=[{'filename':'x.py'}]):
                with self.assertRaisesRegex(SystemExit,'snapshot refused'):current_files('repos/fixture',1,'h')
        for files in ([],[{'filename':'x.py'},{'filename':'x.py'}]):
            with patch('tools.ci_gate.api',side_effect=[pr,pr]),patch('tools.ci_gate.pages',return_value=files):
                with self.assertRaisesRegex(SystemExit,'Incomplete'):current_files('repos/fixture',1,'h')

    def test_exact_head_yaml_selection_ignores_checkout_configuration(self):
        config='on: {pull_request: {paths: ["src/**"]}}\njobs: {}\n'
        with patch('tools.ci_gate.subprocess.check_output',side_effect=['.github/workflows/x.yml\n',config]) as read:
            self.assertEqual({'.github/workflows/x.yml'},expected_workflows(['src/a.py'],head='h'))
        self.assertEqual(['git','show','h:.github/workflows/x.yml'],read.call_args.args[0])

    def test_root_markdown_and_negative_paths(self):
        self.assertFalse(selected({'on':{'pull_request':{'paths-ignore':['**/*.md']}}},['README.md']))
        self.assertFalse(selected({'on':{'pull_request':{'paths':['src/**','!src/excluded/**']}}},['src/excluded/a']))
