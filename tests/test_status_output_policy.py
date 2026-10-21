"""Offline CI fixtures for output guards and protected-main status draft PRs."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.check_status_pr import STATUS_FILES, changed_paths, check
from tools.rebuild_main_status import rebuild, BRANCH_PREFIX

REPO = 'howardweale/lightyear-carddemo-modernization'
BOT = {'user': {'id': 41898282, 'login': 'github-actions[bot]', 'type': 'Bot'},
       'head': {'repo': {'full_name': REPO}, 'ref': BRANCH_PREFIX + 'a' * 40},
       'base': {'ref': 'main'}, 'title': 'status: rebuild after ' + 'a' * 40}


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
        row = copy.deepcopy(BOT); row['base']['ref'] = 'other'; variants.append(row)
        row = copy.deepcopy(BOT); row['head']['ref'] = 'ordinary'; variants.append(row)
        row = copy.deepcopy(BOT); row['title'] += ' extra'; variants.append(row)
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


    def test_disposable_status_baseline_preserves_mutation_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def git(*args):
                return subprocess.run(
                    ['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                     '-c', 'commit.gpgsign=false', *args], cwd=root, capture_output=True)

            def success(*args):
                result = git(*args)
                self.assertEqual(0, result.returncode, result.stderr.decode())
                return result.stdout.decode().strip()

            success('init')
            protected = ('docs/factory/input.json', 'docs/milestones/preserved.json')
            for path in (*STATUS_FILES, *protected):
                dest = root / path; dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('committed input or historical evidence', encoding='utf-8')
            success('add', '.'); success('commit', '-m', 'fixture input change')
            for path in STATUS_FILES:
                (root / path).write_text('fresh generated status for committed input', encoding='utf-8')
            success('add', '--', *sorted(STATUS_FILES))
            self.assertEqual(STATUS_FILES, set(success('diff', '--cached', '--name-only').splitlines()))
            success('diff', '--exit-code')
            # Tests must not alter either generated baseline or any protected input/evidence.
            for path in (*STATUS_FILES, *protected):
                with self.subTest(path=path):
                    original = (root / path).read_bytes()
                    (root / path).write_text('unexpected test mutation', encoding='utf-8')
                    self.assertNotEqual(0, git('diff', '--exit-code').returncode)
                    (root / path).write_bytes(original)
            success('diff', '--exit-code')


class RebuildTests(unittest.TestCase):
    def fixture(self, changed=True, extra=False, deleted=False, mode=False,
                count=0, existing=None, branch_exists=False, advance=False,
                post_error=False, bad_response=False, historical=False, grow_at=None):
        calls=[]; renders=[]; requests=[]; writes=[]; pushes=[]; gates=[]
        source='a'*40; commit='c'*40; branch=BRANCH_PREFIX+source
        def command(*args):
            calls.append(args)
            if args==('rev-parse','FETCH_HEAD'):return source
            if args==('rev-parse','HEAD'):return commit
            if args==('show','-s','--format=%P',commit):return source
            if args==('diff','--name-only'):return '\n'.join(STATUS_FILES) if changed else ''
            if args==('diff','--name-only',source,commit):return '\n'.join(STATUS_FILES)
            if args==('ls-files','--others','--exclude-standard'):return 'unexpected' if extra else ''
            if args==('diff','--name-only','--diff-filter=D'):return next(iter(STATUS_FILES)) if deleted else ''
            if args==('diff','--summary'):return 'mode change 100644 => 100755' if mode else ''
            if args==('ls-remote','origin','refs/heads/main'):
                return ('b'*40 if advance else source)+'\trefs/heads/main'
            if args==('ls-remote','origin','refs/heads/'+branch):
                return commit+'\trefs/heads/'+branch if branch_exists or pushes else ''
            if args[0]=='push':
                # Reproduce the protected-main boundary from the original failure.
                self.assertNotEqual('refs/heads/main',args[-1].split(':')[-1])
                self.assertNotIn('--force',args);pushes.append(args)
            return ''
        def api(route,payload=None):
            requests.append((route,payload))
            if payload is not None:
                writes.append(payload)
                if post_error:raise RuntimeError('ambiguous API failure')
                return {'number':9,'state':'open','draft':True,'base':{'ref':'main'},
                        'head':{'ref':branch,'sha':'d'*40 if bad_response else commit,
                                'repo':{'full_name':REPO}},'html_url':'https://example.invalid/pull/9'}
            if route.startswith('pulls?state=all'):return [{'number':8}] if historical else []
            gates.append(True)
            if existing:return [existing]
            n=6 if grow_at is not None and len(gates)>=grow_at else count
            return [{'head':{'ref':'feature-'+str(i)}} for i in range(n)]
        options=dict(repository=REPO,command=command,render=lambda:renders.append(True),api=api)
        return options,calls,renders,requests,writes,pushes

    def test_protected_main_uses_one_branch_and_draft_without_approving_or_merging(self):
        opts,calls,renders,requests,writes,pushes=self.fixture(count=5)
        result=rebuild(**opts)
        self.assertEqual('draft_created',result['state']);self.assertFalse(result['published_to_main'])
        self.assertEqual(1,len(pushes));self.assertEqual(1,len(renders));self.assertEqual(1,len(writes))
        self.assertTrue(writes[0]['draft']);self.assertEqual('main',writes[0]['base'])
        self.assertIn('approve',writes[0]['body'])
        self.assertEqual(1,len([a for a in calls if 'commit' in a]))
        self.assertTrue(all(route.startswith('pulls') for route,_ in requests))
        check(BOT,STATUS_FILES,REPO)

    def test_unchanged_render_has_no_commit_push_or_api_calls(self):
        opts,calls,_,requests,writes,pushes=self.fixture(changed=False)
        self.assertEqual('unchanged',rebuild(**opts)['state'])
        self.assertFalse(requests or writes or pushes);self.assertFalse(any('commit' in a for a in calls))

    def test_capacity_and_newly_filled_slot_defer_without_pr_creation(self):
        for kwargs in ({'count':6},{'count':7},{'grow_at':2},{'grow_at':3}):
            with self.subTest(kwargs=kwargs):
                opts,_,_,_,writes,pushes=self.fixture(**kwargs)
                result=rebuild(**opts)
                self.assertEqual('awaiting_pr_slot',result['state']);self.assertFalse(writes)
                self.assertEqual(1 if kwargs.get('grow_at')==3 else 0,len(pushes))

    def test_existing_status_pr_preserves_branch_and_human_edits(self):
        pr=copy.deepcopy(BOT);pr.update(number=8,html_url='https://example.invalid/pull/8')
        opts,calls,_,_,writes,pushes=self.fixture(existing=pr)
        self.assertEqual('awaiting_existing_pr',rebuild(**opts)['state'])
        self.assertFalse(writes or pushes);self.assertFalse(any('commit' in a for a in calls))
        pr['user']['id']=7
        opts,_,_,_,writes,pushes=self.fixture(existing=pr)
        with self.assertRaisesRegex(ValueError,'ownership'):rebuild(**opts)
        self.assertFalse(writes or pushes)

    def test_extra_files_deletion_and_mode_changes_refused_before_network_writes(self):
        for kwargs in ({'extra':True},{'deleted':True},{'mode':True}):
            opts,_,_,_,writes,pushes=self.fixture(**kwargs)
            with self.assertRaises(ValueError):rebuild(**opts)
            self.assertFalse(writes or pushes)

    def test_stale_main_existing_branch_and_closed_source_pr_are_not_reused(self):
        for kwargs in ({'advance':True},{'branch_exists':True},{'historical':True}):
            opts,_,renders,_,writes,pushes=self.fixture(**kwargs)
            with self.assertRaises(ValueError):rebuild(**opts)
            self.assertFalse(writes or pushes);self.assertEqual(1,len(renders))

    def test_ambiguous_creation_and_wrong_response_never_repeat_post_or_push(self):
        for kwargs,error in (({'post_error':True},RuntimeError),({'bad_response':True},ValueError)):
            opts,_,_,_,writes,pushes=self.fixture(**kwargs)
            with self.assertRaises(error):rebuild(**opts)
            self.assertEqual(1,len(writes));self.assertEqual(1,len(pushes))

    def test_real_git_status_branch_leaves_main_and_input_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);remote=root/'remote.git';repo=root/'checkout'
            subprocess.check_call(['git','init','--bare',str(remote)],stdout=subprocess.DEVNULL)
            subprocess.check_call(['git','init','-b','main',str(repo)],stdout=subprocess.DEVNULL)
            def command(*args):
                return subprocess.check_output(
                    ['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                     '-c','commit.gpgsign=false',*args],cwd=repo,stderr=subprocess.DEVNULL).decode().strip()
            for name in (*STATUS_FILES,'input.json'):
                p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original\n')
            command('add','.');command('commit','-m','input change')
            source=command('rev-parse','HEAD')
            command('remote','add','origin',str(remote));command('push','origin','main')
            def render():
                for name in STATUS_FILES:(repo/name).write_text('fresh render\n')
            writes=[]
            def api(route,payload=None):
                if payload is None:return []
                writes.append(payload)
                return {'number':1,'draft':True,'state':'open','base':{'ref':'main'},
                        'head':{'sha':command('rev-parse','HEAD'),'ref':payload['head'],
                                'repo':{'full_name':REPO}},'html_url':'https://example.invalid/pull/1'}
            result=rebuild(repository=REPO,command=command,render=render,api=api)
            self.assertEqual('draft_created',result['state']);self.assertEqual(1,len(writes))
            self.assertEqual(source,command('ls-remote','origin','refs/heads/main').split()[0])
            self.assertEqual(source,command('show','-s','--format=%P',result['commit']))
            self.assertEqual(STATUS_FILES,set(command('diff','--name-only',source,result['commit']).splitlines()))
            self.assertEqual('original\n',(repo/'input.json').read_text())
            self.assertFalse(command('status','--porcelain'))
