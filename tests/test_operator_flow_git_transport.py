"""CI-only local Git metadata and command/env boundary checks; no sender."""
import os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import test_operator_flow_ref_lease as fixtures
from tools.ci.operator_flow_git_transport import (
    REMOTE,publisher_git_environment,check_local_transport_config,checked_push_command)

class GitTransportBoundary(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExactRefLease();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.f.root;self.empty=Path(self.f.f.tmp.name)/'empty-hooks';self.empty.mkdir()
    def config(self):return self.f.f.git('config','--local','--no-includes','--null','--list')
    def command(self):return checked_push_command(self.f.c,executable=self.f.E,metadata_head=self.f.M,
        branch_ref=self.f.branch,metadata_root=self.root,empty_hooks=self.empty)
    def test_actual_minimal_local_config_is_checked(self):
        result=check_local_transport_config(self.config(),self.root)
        self.assertEqual(len(result),64)
    def test_actual_local_URL_rewrite_is_refused(self):
        self.f.f.git('config','url.https://example.invalid/.insteadOf','https://github.com/')
        with self.assertRaisesRegex(ValueError,'unapproved-entry'):check_local_transport_config(self.config(),self.root)
    def test_include_is_observed_without_following_it_then_refused(self):
        outside=Path(self.f.f.tmp.name)/'not-loaded';outside.write_text('[injected]\nvalue = must-not-load\n')
        self.f.f.git('config','include.path',str(outside));raw=self.config()
        self.assertNotIn(b'injected.value',raw)
        with self.assertRaisesRegex(ValueError,'unapproved-entry'):check_local_transport_config(raw,self.root)
    def test_credentials_hooks_filters_push_defaults_and_extensions_refuse(self):
        raw=self.config()
        for key in ('credential.helper','core.hookspath','core.fsmonitor','core.sshcommand',
                'filter.fake.clean','push.default','remote.origin.mirror','remotes.all','extensions.worktreeconfig'):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'unapproved-entry'):
                check_local_transport_config(raw+(key+'\nunsafe\0').encode(),self.root)
    def test_duplicate_malformed_or_foreign_origin_config_refuses(self):
        raw=self.config()
        for changed in (raw+b'core.bare\nfalse\0',raw[:-1],raw+b'bad-record\0',
                raw+b'remote.origin.url\nhttps://example.invalid/other\0remote.origin.fetch\n+refs/heads/*:refs/remotes/origin/*\0'):
            with self.subTest(length=len(changed)),self.assertRaises(ValueError):check_local_transport_config(changed,self.root)
    def test_child_environment_keeps_original_exclusions_and_drops_Git_overrides(self):
        # Only inert sentinels; no credential/provider/GitHub operation occurs.
        fake={'OPENAI_API_KEY':'inert','FACTORY_TRANSPORT_KEY':'inert','FACTORY_CANDIDATE_SIGNING_KEY':'inert',
            'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'url.fake.insteadOf','GIT_CONFIG_VALUE_0':'inert',
            'GIT_TRACE':'inert','GIT_SSH_COMMAND':'inert','SSH_ASKPASS':'inert','GH_DEBUG':'inert'}
        with patch.dict(os.environ,fake):
            env=publisher_git_environment()
            self.assertTrue(all(k not in env for k in fake))
            self.assertEqual(env['GIT_CONFIG_NOSYSTEM'],'1');self.assertEqual(env['GIT_CONFIG_GLOBAL'],os.devnull)
            self.assertEqual(env['GIT_CONFIG_SYSTEM'],os.devnull);self.assertEqual(env['GIT_TERMINAL_PROMPT'],'0')
            self.assertEqual(os.environ['GIT_TRACE'],'inert')
    def test_fixed_remote_single_ref_no_signing_tags_or_recursion(self):
        command=self.command();self.assertEqual(command[-2],REMOTE)
        self.assertEqual(command[-1],self.f.M+':'+self.f.branch)
        self.assertEqual(sum(x.startswith('--force-with-lease=') for x in command),1)
        self.assertIn('--signed=false',command);self.assertIn('--no-follow-tags',command)
        self.assertIn('--recurse-submodules=no',command);self.assertNotIn('--force',command)
        self.assertNotIn('--mirror',command);self.assertNotIn('--all',command)
        self.assertIn('credential.helper=!gh auth git-credential',command)
    def test_hook_tree_inside_M_or_main_ref_refuses(self):
        with self.assertRaisesRegex(ValueError,'independent-paths'):
            checked_push_command(self.f.c,executable=self.f.E,metadata_head=self.f.M,
                branch_ref=self.f.branch,metadata_root=self.root,empty_hooks=self.root/'hooks')
        with self.assertRaisesRegex(ValueError,'codex-branch'):
            checked_push_command(self.f.c,executable=self.f.E,metadata_head=self.f.M,
                branch_ref='refs/heads/main',metadata_root=self.root,empty_hooks=self.empty)
