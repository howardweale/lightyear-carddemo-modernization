"""Synthetic terminal and file ports. No host observation, engine, key or network."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import h1_operator_controls as c
from tools import intcalc_private_reference_host as h


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.p = dict(schema='ha-private-host-profile/1', source_commit='1'*40, source_tree='2'*40,
                      private_root='/synthetic/hidden-root', client_config='/synthetic/config',
                      dockerd_sha256='3'*64,
                      binaries={n: dict(path='/synthetic/bin/'+n, sha256='4'*64) for n in h.BINS})
        self.files = {}
        self.output = StringIO()
        self.prompts = []
        self.when = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        self.minutes = '120'
        self.reject = ''
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(c, 'make_profile', return_value=self.p))
        stack.enter_context(patch.object(c, 'load_file', side_effect=lambda d, n: self.files[n]))
        stack.enter_context(patch.object(h, 'private_control_file'))
        stack.enter_context(patch.object(h, 'exclusive', side_effect=self.create))
        stack.enter_context(patch.object(Path, 'iterdir', side_effect=lambda: iter(self.files)))
        stack.enter_context(redirect_stdout(self.output))

    def create(self, path, raw):
        if path.name in self.files:
            raise FileExistsError
        self.files[path.name] = raw

    def ask(self, prompt):
        self.prompts.append(prompt)
        if 'group state' in prompt:
            return 'ABSENT'
        if 'whole minutes' in prompt:
            return self.minutes
        token = prompt.split('Type ')[1].split()[0]
        return 'unknown' if token == self.reject else token

    def phase(self, name):
        c.operate(name, Path('/synthetic'), self.ask, visible=input, now=lambda: self.when)

    def test_written_bytes_pass_merged_h1_validators_and_joins(self):
        self.phase('PREFLIGHT')
        p = h.strict(self.files['PROFILE.json'])
        h.profile(p)
        operation = self.files['OPERATION-ID.txt'].decode().strip()
        pre = h.strict(self.files['CUSTODY.json'])
        ph = h.sha(h.canonical(p))
        h.custody(pre, operation, ph, p['source_commit'], p['source_tree'])
        self.assertEqual(set(pre['checks']), set(h.PRE + h.POST))
        self.assertTrue(all(pre['checks'][key] is False for key in h.POST))
        start = self.when
        for mode in c.MODES:
            self.when += timedelta(minutes=5)
            self.phase(mode)
            raw = self.files[mode+'-APPROVAL.json']
            row = h.strict(raw)
            h.approval(row, h.sha(raw), raw, p, mode, self.when)
            self.assertEqual(row['operation_id'], operation)
            self.assertEqual(row['custody_sha256'], h.sha(self.files['CUSTODY.json']))
            self.assertEqual(h.aware(row['valid_from']), start)
            self.assertEqual(h.aware(row['expires_at']), start+timedelta(hours=2))
        self.when += timedelta(minutes=10)
        self.phase('POSTFLIGHT')
        post = h.strict(self.files['POSTFLIGHT.json'])
        h.custody(post, operation, ph, p['source_commit'], p['source_tree'], post=True)
        self.assertEqual(h.aware(post['observed_at_with_offset']), self.when)
        self.assertEqual(self.output.getvalue().splitlines(),
                         [name+' '+h.sha(raw) for name, raw in self.files.items()])

    def test_every_group_requires_deliberate_confirmation(self):
        for group in c.GROUPS:
            self.reject = group
            with self.subTest(group=group), self.assertRaises(ValueError):
                self.phase('PREFLIGHT')
            self.assertFalse(self.files)

    def test_postflight_cannot_be_precreated_or_implicitly_confirmed(self):
        self.phase('PREFLIGHT')
        with self.assertRaises(KeyError):
            self.phase('POSTFLIGHT')
        self.phase('QUALIFY_PUBLIC')
        for fail in ('POSTFLIGHT', *c.GROUPS):
            self.reject = fail
            with self.assertRaises(ValueError):
                self.phase('POSTFLIGHT')
            self.assertNotIn('POSTFLIGHT.json', self.files)

    def test_approval_not_extended_or_overwritten(self):
        self.phase('PREFLIGHT')
        for minutes in ('0', '121'):
            self.minutes = minutes
            with self.assertRaises(ValueError):
                self.phase('INSPECT')
        self.minutes = '120'
        self.phase('INSPECT')
        old = self.files['INSPECT-APPROVAL.json']
        with self.assertRaises(FileExistsError):
            self.phase('INSPECT')
        self.assertEqual(self.files['INSPECT-APPROVAL.json'], old)
        self.when += timedelta(hours=2)
        with self.assertRaises(h.Refused):
            self.phase('QUALIFY_PUBLIC')

    def test_changed_preflight_refuses_postflight(self):
        self.phase('PREFLIGHT')
        self.phase('QUALIFY_PUBLIC')
        self.files['CUSTODY.json'] += b'\n'
        with self.assertRaises(ValueError):
            self.phase('POSTFLIGHT')

    def test_no_mode_approval_by_default(self):
        self.phase('PREFLIGHT')
        for mode in c.MODES:
            self.reject = mode
            with self.assertRaises(ValueError):
                self.phase(mode)
            self.assertNotIn(mode+'-APPROVAL.json', self.files)


class TerminalTests(unittest.TestCase):
    def test_profile_echoes_only_reviewed_source_and_binary_paths(self):
        visible = []
        hidden = []

        def read_visible(prompt):
            visible.append(prompt)
            if 'commit' in prompt or 'tree' in prompt:
                return '1' * 40
            return '/synthetic/bin/' + prompt.split()[-1].rstrip(':')

        def read_hidden(prompt):
            hidden.append(prompt)
            return '/synthetic/private'

        with (patch.object(h, 'private_directory', side_effect=Path),
              patch.object(Path, 'is_absolute', return_value=True),
              patch.object(Path, 'resolve', autospec=True, side_effect=lambda p, strict: p),
              patch.object(h, 'read', return_value=b'tool'), patch.object(h, 'profile')):
            c.make_profile(read_hidden, read_visible)
        self.assertEqual(visible, ['Reviewed wrapper commit: ', 'Reviewed wrapper tree: '] +
                         ['Installed absolute path for ' + n + ': ' for n in (*h.BINS, 'dockerd')])
        self.assertEqual(hidden, ['Private root: ', 'Empty Docker configuration directory: '])

    def test_cli_exposes_only_closed_refusal_codes(self):
        for error, expected in ((ValueError('window'), 'window'),
                                (h.Refused('host-profile'), 'host-profile'),
                                (ValueError('/synthetic/private'), 'operator-fault'),
                                (OSError('/synthetic/private'), 'operator-fault')):
            with self.subTest(expected=expected), patch.object(c, 'main', side_effect=error):
                output = StringIO()
                with redirect_stderr(output):
                    self.assertEqual(c.cli(['PREFLIGHT']), 2)
                self.assertEqual(output.getvalue(), 'operator-controls-refused ' + expected + '\n')
