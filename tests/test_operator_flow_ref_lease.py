"""Real local Git receive-pack lease tests in CI; inert invalid proof bytes.

No GitHub endpoint, credential, signing, native proof or qualification claim.
"""
import copy,os,subprocess,unittest
from pathlib import Path
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_ref_lease import exact_ref_lease
from tools.ci.operator_flow_metadata import object_id

class ExactRefLease(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.f=fixtures.MetadataObjects();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.ancestor=self.f.head
        self.f.git('commit','--allow-empty','-m','second inert E')
        self.f.head=self.f.git('rev-parse','HEAD').decode().strip()
        self.c=self.f.build();self.E=self.f.head;self.M=self.c['commit']
        self.branch='refs/heads/codex/disposable-ref-lease'
        self.remote=Path(self.f.tmp.name)/'remote.git'
        subprocess.run(['git','clone','--bare','--no-hardlinks',str(self.f.root),str(self.remote)],
            check=True,capture_output=True,env=self.f.env)
        self.rgit('update-ref',self.branch,self.E)
        self.rgit('update-ref','refs/heads/main',self.E)
        self.rgit('update-ref','refs/tags/retained',self.E)
        for oid,(kind,raw) in self.c['objects'].items():
            self.assertEqual(self.f.git('hash-object','-w','-t',kind,'--stdin',data=raw).decode().strip(),oid)
    def rgit(self,*args):return self.f.git(*args,root=self.remote)
    def plan(self):return exact_ref_lease(self.c,executable=self.E,metadata_head=self.M,branch_ref=self.branch)
    def push(self):
        args=self.plan()
        return subprocess.run(['git','-C',str(self.f.root),'push',*args[:-1],str(self.remote),args[-1]],
            capture_output=True,env=self.f.env,timeout=30)
    def test_exact_E_fast_forward_updates_only_named_branch(self):
        before=self.rgit('show-ref').decode().splitlines();self.assertEqual(self.push().returncode,0)
        self.assertEqual(self.rgit('rev-parse',self.branch).decode().strip(),self.M)
        after=self.rgit('show-ref').decode().splitlines()
        self.assertEqual([x for x in before if not x.endswith(' '+self.branch)],
            [x for x in after if not x.endswith(' '+self.branch)])
        self.assertFalse(self.c['publication_authorized'])
    def test_concurrent_other_commit_is_not_overwritten(self):
        self.f.git('commit','--allow-empty','-m','concurrent other work')
        other=self.f.git('rev-parse','HEAD').decode().strip()
        self.f.git('push',str(self.remote),other+':'+self.branch)
        self.assertNotEqual(self.push().returncode,0)
        self.assertEqual(self.rgit('rev-parse',self.branch).decode().strip(),other)
    def test_deleted_branch_is_not_recreated(self):
        self.rgit('update-ref','-d',self.branch)
        self.assertNotEqual(self.push().returncode,0)
        p=subprocess.run(['git','-C',str(self.remote),'show-ref','--verify',self.branch],capture_output=True)
        self.assertNotEqual(p.returncode,0)
    def test_rewind_to_ancestor_refuses_even_though_M_is_fast_forward(self):
        self.rgit('update-ref',self.branch,self.ancestor,self.E)
        self.assertNotEqual(self.push().returncode,0)
        self.assertEqual(self.rgit('rev-parse',self.branch).decode().strip(),self.ancestor)
    def test_tracking_ref_movement_cannot_change_explicit_expectation(self):
        self.rgit('update-ref',self.branch,self.ancestor,self.E)
        self.f.git('update-ref','refs/remotes/origin/disposable-ref-lease',self.ancestor)
        self.assertIn('--force-with-lease='+self.branch+':'+self.E,self.plan())
        self.assertNotEqual(self.push().returncode,0)
    def test_main_tags_wildcards_and_option_injection_refuse(self):
        for ref in ('refs/heads/main','refs/tags/retained','refs/heads/codex/*',
                'refs/heads/codex/a:b','refs/heads/codex/a..b','--all','refs/heads/codex/a b'):
            with self.subTest(ref=ref),self.assertRaisesRegex(ValueError,'codex-branch'):
                exact_ref_lease(self.c,executable=self.E,metadata_head=self.M,branch_ref=ref)
    def test_non_fast_forward_or_extra_parent_bytes_refuse(self):
        for parent in ('parent '+self.ancestor,'parent '+self.E+'\nparent '+self.ancestor):
            c=copy.deepcopy(self.c);raw=c['objects'][self.M][1].replace(('parent '+self.E).encode(),parent.encode())
            oid=object_id('commit',raw);c['objects'][oid]=('commit',raw);c['commit']=oid
            with self.assertRaisesRegex(ValueError,'sole-parent-bytes'):
                exact_ref_lease(c,executable=self.E,metadata_head=oid,branch_ref=self.branch)
    def test_asserted_authority_boolean_epoch_and_wrong_M_refuse(self):
        c=copy.deepcopy(self.c);c['publication_authorized']=True
        with self.assertRaisesRegex(ValueError,'no-authority'):
            exact_ref_lease(c,executable=self.E,metadata_head=self.M,branch_ref=self.branch)
        self.c['commit_epoch']=True
        with self.assertRaisesRegex(ValueError,'commit-fields'):self.plan()
        with self.assertRaisesRegex(ValueError,'no-authority'):
            exact_ref_lease(c,executable=self.E,metadata_head='0'*40,branch_ref=self.branch)
