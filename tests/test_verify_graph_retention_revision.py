"""Native checkout-log and source commit bindings, with no retention writes."""
import copy,io,stat,unittest,zipfile
from tools.ci.verify_graph_retention import checkout_revision,revision_relationship

class TestedGraphRevision(unittest.TestCase):
    def setUp(self):
        self.head='a'*40;self.base='b'*40;self.merge='c'*40
        self.run=dict(event='pull_request',head_sha=self.head)
        self.commit=dict(sha=self.merge,parents=[dict(sha=self.base),dict(sha=self.head)])
        self.job=dict(steps=[dict(number=2,name='Run actions/checkout@v7',status='completed',conclusion='success')])
    def archive(self,body=None,duplicate=False,symlink=False,extra=None):
        sha=self.merge
        lines=body if body is not None else ['  ref: '+sha,'[command]/usr/bin/git checkout --progress --force '+sha,
            '[command]/usr/bin/git log -1 --format=%H',sha]
        raw=''.join('2026-10-30T20:13:20.0570304Z '+line+'\n' for line in lines).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            item=zipfile.ZipInfo('isolated-judge/2_Run actions_checkout@v7.txt')
            item.external_attr=((stat.S_IFLNK if symlink else stat.S_IFREG)|0o644)<<16
            z.writestr(item,raw)
            if duplicate:z.writestr(item,raw)
            if extra:z.writestr(*extra)
        return out.getvalue()
    def test_original_checkout_and_merge_parents_join(self):
        revision=checkout_revision(self.archive(),self.job)
        self.assertEqual(revision,self.merge)
        self.assertEqual(revision_relationship(self.run,revision,self.commit),self.merge)
    def test_later_step_report_cannot_supply_checkout_revision(self):
        fake=b'2026-10-30T20:13:30.000Z [command]/usr/bin/git log -1 --format=%H\n2026-10-30T20:13:30.001Z '+b'd'*40+b'\n'
        self.assertEqual(checkout_revision(self.archive(extra=('isolated-judge/6_Report.txt',fake)),self.job),self.merge)
    def test_wrong_or_failed_checkout_step_refuses(self):
        for key,value in (('number',3),('name','user script'),('status','in_progress'),('conclusion','failure')):
            job=copy.deepcopy(self.job);job['steps'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):checkout_revision(self.archive(),job)
    def test_duplicate_or_symlink_log_refuses(self):
        for options in (dict(duplicate=True),dict(symlink=True)):
            with self.subTest(options=options),self.assertRaises(ValueError):checkout_revision(self.archive(**options),self.job)
    def test_missing_ambiguous_or_crossed_log_revision_refuses(self):
        for lines in ([],['[command]/usr/bin/git log -1 --format=%H'],
            ['  ref: '+self.head,'[command]/usr/bin/git checkout --progress --force '+self.merge,'[command]/usr/bin/git log -1 --format=%H',self.merge],
            ['  ref: '+self.merge,'[command]/usr/bin/git checkout --progress --force '+self.merge,'[command]/usr/bin/git log -1 --format=%H',self.merge,'[command]/usr/bin/git log -1 --format=%H',self.merge]):
            with self.subTest(lines=lines),self.assertRaises(ValueError):checkout_revision(self.archive(body=lines),self.job)
    def test_branch_head_cannot_replace_tested_PR_merge(self):
        with self.assertRaises(ValueError):revision_relationship(self.run,self.head,self.commit)
    def test_crossed_missing_extra_or_reordered_merge_parents_refuse(self):
        for parents in ([],[self.head],[self.base,'d'*40],[self.head,self.base],[self.base,self.head,'d'*40],[self.head,self.head]):
            with self.subTest(parents=parents),self.assertRaises(ValueError):
                revision_relationship(self.run,self.merge,dict(sha=self.merge,parents=[dict(sha=p) for p in parents]))
    def test_native_commit_identity_must_match_checkout(self):
        with self.assertRaises(ValueError):revision_relationship(self.run,self.merge,dict(self.commit,sha='d'*40))
    def test_push_keeps_exact_branch_head_contract(self):
        run=dict(event='push',head_sha=self.head)
        self.assertEqual(revision_relationship(run,self.head,dict(sha=self.head)),self.head)
        with self.assertRaises(ValueError):revision_relationship(run,self.merge,self.commit)
    def test_unknown_event_refuses(self):
        with self.assertRaises(ValueError):revision_relationship(dict(self.run,event='workflow_dispatch'),self.merge,self.commit)


class CheckoutLogBomTests(unittest.TestCase):
    """Service UTF-8 BOM is framing, not an alternate checkout identity."""
    def fixture(self, prefix=b'', inside=b''):
        revision='a'*40
        lines=['  ref: '+revision,
               '[command]/usr/bin/git checkout --progress --force '+revision,
               '[command]/usr/bin/git log -1 --format=%H',revision]
        parts=[('2026-11-01T03:19:25.7411455Z '+s+'\n').encode() for s in lines]
        raw=prefix+parts[0]+inside+b''.join(parts[1:])
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            info=zipfile.ZipInfo('isolated-judge/2_Run actions_checkout@v7.txt')
            info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,raw)
        job=dict(steps=[dict(number=2,name='Run actions/checkout@v7',
                            status='completed',conclusion='success')])
        return out.getvalue(),job,revision

    def test_single_leading_bom_and_no_bom_bind_same_revision(self):
        for prefix in (b'',b'\xef\xbb\xbf'):
            with self.subTest(prefix=prefix):
                raw,job,expected=self.fixture(prefix)
                self.assertEqual(checkout_revision(raw,job),expected)

    def test_repeated_or_embedded_bom_remains_refused(self):
        for prefix,inside in ((b'\xef\xbb\xbf'*2,b''),
                              (b'',b'\xef\xbb\xbf'),
                              (b'\xef\xbb\xbf',b'\xef\xbb\xbf')):
            with self.subTest(prefix=prefix,inside=inside):
                raw,job,_=self.fixture(prefix,inside)
                with self.assertRaisesRegex(ValueError,'^checkout-log-framing$'):
                    checkout_revision(raw,job)

    def test_invalid_utf8_is_not_replaced_or_ignored(self):
        raw,job,_=self.fixture(b'\xff')
        with self.assertRaises(UnicodeDecodeError):
            checkout_revision(raw,job)
