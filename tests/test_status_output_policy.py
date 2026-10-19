"""Offline CI fixtures for output guards and bounded main status publication."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.check_status_pr import STATUS_FILES, changed_paths, check
from tools.rebuild_main_status import rebuild, STATUS_FILES as REBUILT_FILES

REPO = 'howardweale/lightyear-carddemo-modernization'
BOT = {'user': {'id': 41898282, 'login': 'github-actions[bot]', 'type': 'Bot'},
       'head': {'repo': {'full_name': REPO}}, 'title': 'status: rebuild after ' + 'a' * 40}


class OutputGuardTests(unittest.TestCase):
    def test_human_output_diff_refused_but_inputs_allowed(self):
        check({}, ['tools/build_factory_current_status.py', 'docs/factory/new-input.json'], REPO)
        for path in STATUS_FILES:
            with self.assertRaisesRegex(ValueError, 'rebuilt on main'):
                check({}, [path], REPO)

    def test_bot_identity_and_scope_cannot_be_spoofed(self):
        check(BOT, STATUS_FILES, REPO)
        variants = []
        for key, value in [('id', 7), ('id', True), ('login', 'github-actions'), ('type', 'User')]:
            row = copy.deepcopy(BOT); row['user'][key] = value; variants.append(row)
        row = copy.deepcopy(BOT); row['head']['repo']['full_name'] = 'attacker/fork'; variants.append(row)
        row = copy.deepcopy(BOT); row['title'] = 'ordinary change'; variants.append(row)
        for row in variants:
            with self.assertRaises(ValueError): check(row, STATUS_FILES, REPO)
        with self.assertRaises(ValueError): check(BOT, [*STATUS_FILES, 'tools/example.py'], REPO)

    def test_fixture_pr_diff_modification_deletion_and_rename(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def git(*args):
                return subprocess.check_output(['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                                                '-c', 'commit.gpgsign=false', *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            for path in STATUS_FILES:
                dest=root/path; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text('original')
            git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            (root/'docs/factory/current-status.json').write_text('edited')
            (root/'docs/factory/current-status.md').rename(root/'docs/factory/renamed.md')
            git('add','-A');git('commit','-m','fixture PR');head=git('rev-parse','HEAD')
            paths=changed_paths(base,head,cwd=root)
            self.assertTrue(STATUS_FILES <= set(paths))
            with self.assertRaises(ValueError):check({},paths,REPO)


class RebuildTests(unittest.TestCase):
    def fixture(self, changed=True, advance=False, extra=False, deleted=False):
        calls=[]; renders=[]; pushes=[]; fetches=[]
        def command(*args):
            calls.append(args)
            if args[0]=='fetch':fetches.append(True)
            if args==('rev-parse','FETCH_HEAD'):return ('b' if len(fetches)>1 else 'a')*40
            if args==('rev-parse','HEAD'):return 'c'*40
            if args==('diff','--name-only'):return '\n'.join(STATUS_FILES) if changed else ''
            if args==('ls-files','--others','--exclude-standard'):return 'unexpected' if extra else ''
            if args==('diff','--name-only','--diff-filter=D'):return next(iter(STATUS_FILES)) if deleted else ''
            if args==('ls-remote','origin','refs/heads/main'):return ('b' if advance else 'a')*40+'\trefs/heads/main'
            return ''
        def push():
            pushes.append(True)
            return 1 if advance and len(pushes)==1 else 0
        return command, lambda:renders.append(True), push, calls, renders, pushes

    def test_input_change_produces_one_bot_commit(self):
        command,render,push,calls,renders,pushes=self.fixture()
        result=rebuild(command=command,render=render,push=push)
        self.assertTrue(result['changed']);self.assertEqual(1,len(pushes));self.assertEqual(1,len(renders))
        commits=[a for a in calls if 'commit' in a]
        self.assertEqual(1,len(commits));self.assertEqual('status: rebuild after '+'a'*40,commits[0][-1])
        self.assertIn(('add','--',*REBUILT_FILES),calls)

    def test_no_change_produces_no_commit_or_push(self):
        command,render,push,calls,_,pushes=self.fixture(changed=False)
        self.assertFalse(rebuild(command=command,render=render,push=push)['changed'])
        self.assertFalse(pushes);self.assertFalse(any('commit' in a for a in calls))

    def test_concurrent_advance_rebuilds_before_retry(self):
        command,render,push,calls,renders,pushes=self.fixture(advance=True)
        self.assertEqual('b'*40,rebuild(command=command,render=render,push=push)['source'])
        self.assertEqual(2,len(renders));self.assertEqual(2,len(pushes))
        self.assertFalse(any('--force' in a for a in calls))

    def test_unrelated_output_or_deletion_refused(self):
        for kwargs in [{'extra':True},{'deleted':True}]:
            command,render,push,_,_,pushes=self.fixture(**kwargs)
            with self.assertRaises(ValueError):rebuild(command=command,render=render,push=push)
            self.assertFalse(pushes)

    def test_permission_failure_is_not_retried_as_concurrency(self):
        command,render,_,_,renders,_=self.fixture()
        with self.assertRaisesRegex(RuntimeError,'permissions'):
            rebuild(command=command,render=render,push=lambda:1)
        self.assertEqual(1,len(renders))
