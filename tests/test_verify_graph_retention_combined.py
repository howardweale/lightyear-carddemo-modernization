"""Both service log layouts preserve the same checkout identity contract."""
import copy
import io
import stat
import unittest
import warnings
import zipfile

from tools.ci.verify_graph_retention import checkout_revision


class CombinedCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a'*40
        self.job = {'steps': [
            dict(number=2, name='Run actions/checkout@v7', status='completed', conclusion='success'),
            dict(number=3, name='Run actions/setup-java@v5', status='completed', conclusion='success')]}

    def section(self):
        return ['##[group]Run actions/checkout@v7', 'with:', '  ref: '+self.sha,
                '##[endgroup]', '##[group]Checking out the ref',
                '[command]/usr/bin/git checkout --progress --force '+self.sha,
                '##[endgroup]', '[command]/usr/bin/git log -1 --format=%H', self.sha]

    def combined(self, section=None):
        return ['##[group]Runner Image', 'public image', '##[endgroup]'] + (
            self.section() if section is None else section) + [
                '##[group]Run actions/setup-java@v5', 'with:', '##[endgroup]',
                '##[group]Run later public verification', '##[endgroup]']

    def encoded(self, lines):
        return ''.join('2026-11-18T05:19:07.4413640Z '+s+'\n' for s in lines).encode()

    def archive(self, lines=None, *, combined=True, extra=(), prefix=b'', symlink=False):
        name = '0_isolated-judge.txt' if combined else 'isolated-judge/2_Run actions_checkout@v7.txt'
        raw = self.encoded(self.combined() if lines is None and combined else
                           self.section() if lines is None else lines)
        stream = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
            warnings.simplefilter('ignore', UserWarning)
            item = zipfile.ZipInfo(name)
            item.external_attr = ((stat.S_IFLNK if symlink else stat.S_IFREG)|0o644)<<16
            z.writestr(item, prefix+raw)
            for member, value in extra:
                z.writestr(member, value)
        return stream.getvalue()

    def test_both_layouts_bind_identical_revision(self):
        for combined in (False, True):
            for prefix in (b'', b'\xef\xbb\xbf'):
                with self.subTest(combined=combined, prefix=prefix):
                    self.assertEqual(checkout_revision(self.archive(combined=combined, prefix=prefix), self.job), self.sha)

    def test_matching_dual_layout_is_unambiguous(self):
        extra = [('isolated-judge/2_Run actions_checkout@v7.txt', self.encoded(self.section()))]
        self.assertEqual(checkout_revision(self.archive(extra=extra), self.job), self.sha)

    def test_disagreeing_dual_layout_refuses(self):
        changed = [s.replace(self.sha, 'b'*40) for s in self.section()]
        extra = [('isolated-judge/2_Run actions_checkout@v7.txt', self.encoded(changed))]
        with self.assertRaisesRegex(ValueError, '^checkout-log-ambiguous$'):
            checkout_revision(self.archive(extra=extra), self.job)

    def test_later_commands_do_not_enter_checkout_section(self):
        lines = self.combined()+['  ref: '+'b'*40,
            '[command]/usr/bin/git checkout --progress --force '+'b'*40,
            '[command]/usr/bin/git log -1 --format=%H', 'b'*40]
        self.assertEqual(checkout_revision(self.archive(lines), self.job), self.sha)

    def test_missing_and_duplicate_action_boundaries_refuse(self):
        for marker in ('##[group]Run actions/checkout@v7', '##[group]Run actions/setup-java@v5'):
            for lines in ([s for s in self.combined() if s != marker], self.combined()+[marker]):
                with self.subTest(marker=marker, lines=lines), self.assertRaises(ValueError):
                    checkout_revision(self.archive(lines), self.job)

    def test_unexpected_step_before_or_within_checkout_refuses(self):
        for lines in (['##[group]Run untrusted step', '##[endgroup]']+self.combined(),
                      self.combined(self.section()+['##[group]Run untrusted step', '##[endgroup]'])):
            with self.subTest(lines=lines), self.assertRaisesRegex(ValueError, '^checkout-log-ambiguous$'):
                checkout_revision(self.archive(lines), self.job)

    def test_nested_unclosed_or_extra_end_group_refuses(self):
        for section in (self.section()+['##[group]unfinished'], self.section()+['##[endgroup]'],
                        ['##[group]outer']+self.section()+['##[endgroup]']):
            with self.subTest(section=section), self.assertRaises(ValueError):
                checkout_revision(self.archive(self.combined(section)), self.job)

    def test_api_following_step_is_required_and_exact(self):
        for key, value in (('number', 4), ('name', 'Run arbitrary code'),
                           ('status', 'in_progress'), ('conclusion', 'failure')):
            job = copy.deepcopy(self.job)
            job['steps'][1][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, '^checkout-log-boundary$'):
                checkout_revision(self.archive(), job)
        job = copy.deepcopy(self.job)
        job['steps'].append(copy.deepcopy(job['steps'][1]))
        with self.assertRaises(ValueError):
            checkout_revision(self.archive(), job)

    def test_revision_checks_unchanged_for_both_layouts(self):
        broken = [self.section()[:-1],
                  [s.replace('  ref: '+self.sha, '  ref: '+'b'*40) for s in self.section()],
                  [s.replace('checkout --progress --force', 'checkout --force') for s in self.section()],
                  self.section()+['[command]/usr/bin/git log -1 --format=%H', self.sha]]
        for combined in (False, True):
            for section in broken:
                with self.subTest(combined=combined, section=section), self.assertRaises(ValueError):
                    checkout_revision(self.archive(self.combined(section) if combined else section,
                                                   combined=combined), self.job)

    def test_no_boundary_borrowing_from_system_entry(self):
        extra = [('isolated-judge/system.txt', self.encoded(self.combined()))]
        with self.assertRaises(ValueError):
            checkout_revision(self.archive([], extra=extra), self.job)

    def test_duplicate_archive_members_and_symlinks_refuse(self):
        for combined in (False, True):
            name = '0_isolated-judge.txt' if combined else 'isolated-judge/2_Run actions_checkout@v7.txt'
            for options in (dict(symlink=True), dict(extra=[(name, b'other')])):
                with self.subTest(combined=combined, options=options), self.assertRaises(ValueError):
                    checkout_revision(self.archive(combined=combined, **options), self.job)

    def test_same_archive_entry_and_size_limits(self):
        for combined in (False, True):
            for options in (dict(extra=[('other-'+str(i), b'') for i in range(64)]),
                            dict(prefix=b'x'*(1024*1024)), dict(prefix=b'x'*(8*1024*1024))):
                with self.subTest(combined=combined, options=options), self.assertRaises(ValueError):
                    checkout_revision(self.archive(combined=combined, **options), self.job)

    def test_utf8_and_timestamp_framing_unchanged(self):
        for combined in (False, True):
            for prefix in (b'\xff', b'\xef\xbb\xbf'*2, b'no timestamp\n'):
                with self.subTest(combined=combined, prefix=prefix), self.assertRaises(ValueError):
                    checkout_revision(self.archive(combined=combined, prefix=prefix), self.job)

    def test_reordered_boundaries_refuse(self):
        lines = ['##[group]Run actions/setup-java@v5', '##[endgroup]']+self.section()
        with self.assertRaisesRegex(ValueError, '^checkout-log-boundary$'):
            checkout_revision(self.archive(lines), self.job)
