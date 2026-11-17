"""Public synthetic ports tests; never a generator or a model invocation."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory import public_repair_durable as d


class SerializationTests(unittest.TestCase):
    def test_canonical_matches_controller_bytes(self):
        from lightyear_factory.public_repair_controller import canonical
        row = {'z': [True, None, '\u00e9', 5], 'a': {'n': -4}}
        self.assertEqual(d.canonical(row), canonical(row))

    def test_float_nonfinite_and_nonjson_refused(self):
        for value in (1.0, float('inf'), float('nan'), b'x', {1: 'x'}, (1,)):
            with self.subTest(kind=type(value).__name__), self.assertRaisesRegex(d.Refused, 'durable-json'):
                d.canonical({'value': value})

    def test_recursion_and_capacity_refused(self):
        row = []; row.append(row)
        with self.assertRaisesRegex(d.Refused, 'durable-json'):
            d.canonical({'cycle': row})
        with self.assertRaisesRegex(d.Refused, 'durable-cap'):
            d.canonical({'x': 'x' * d.RECORD_BYTES})

    def test_fixed_fault_record_has_no_exception_text(self):
        row = d.Refused('durable-io', 'file', errno.EIO).public_record()
        self.assertEqual(row, {'refusal_code': 'durable-io', 'file_kind': 'file', 'errno': errno.EIO})
        dynamic = d.Refused('private-path-content', '/host/path', 'private-value')
        self.assertEqual(dynamic.public_record(), {'refusal_code': 'durable-io', 'file_kind': 'none', 'errno': None})
        self.assertEqual(str(dynamic), 'durable-io')

    def test_nonposix_before_platform_specific_names(self):
        with patch.object(d.os, 'name', 'nt'):
            with self.assertRaisesRegex(d.Refused, 'durable-posix-required'):
                d.DurablePorts('not-a-path', 'a' * 64, 100)
            with self.assertRaisesRegex(d.Refused, 'durable-posix-required'):
                d.full_sync(-1, 'file')

    def test_mac_fullsync_no_fallback_and_fixed_errno(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(d.Refused, 'durable-posix-required'):
                d.full_sync(-1, 'file')
            return
        import fcntl
        with patch.object(d.sys, 'platform', 'darwin'), \
                patch.object(fcntl, 'F_FULLFSYNC', 51, create=True), \
                patch.object(fcntl, 'fcntl') as full, patch.object(d.os, 'fsync') as fallback:
            d.full_sync(12, 'file')
            full.assert_called_once_with(12, 51)
            fallback.assert_not_called()
            full.side_effect = OSError(errno.EIO, 'sensitive/path')
            with self.assertRaises(d.Refused) as caught:
                d.full_sync(12, 'directory')
            self.assertEqual(str(caught.exception), 'durable-full-sync')
            self.assertEqual(caught.exception.error_number, errno.EIO)
            fallback.assert_not_called()


class DurablePortsTests(unittest.TestCase):
    def setUp(self):
        self.ports = None
        self.now = 100
        self.temp = tempfile.TemporaryDirectory(prefix='public-durable-', dir=Path.home().resolve())
        self.parent = Path(self.temp.name).resolve()
        if os.name == 'posix':
            self.parent.chmod(0o700)

    def tearDown(self):
        if self.ports is not None:
            self.ports.close()
        self.temp.cleanup()

    def available(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(d.Refused, 'durable-posix-required'):
                d.DurablePorts(str(self.parent), 'a' * 64, 200, clock=lambda: self.now)
            self.assertEqual(list(self.parent.iterdir()), [])
            return False
        return True

    def create(self, run_id='a' * 64):
        self.ports = d.DurablePorts(str(self.parent), run_id, 200, clock=lambda: self.now)
        return self.ports

    def root(self):
        return self.parent / ('public-repair-' + 'a' * 64)

    def test_actual_volume_sync_record_and_artifact_readback(self):
        if not self.available():
            return
        p = self.create()
        row = {'public': True, 'counts': [1, 2], 'status': 'SYNTHETIC'}
        expected = d.canonical(row) + b'\n'
        self.assertEqual(p.record('attempt-0', row), hashlib.sha256(expected).hexdigest())
        raw = (self.root() / 'record-attempt-0.json').read_bytes()
        self.assertEqual(raw, expected)
        source = 'public class Main {}\n'
        self.assertEqual(p.retain_artifact('builder-0', 'source', source),
                         hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual((self.root() / 'artifact-builder-0-source.txt').read_bytes(), source.encode())
        self.assertEqual(stat.S_IMODE(self.root().stat().st_mode), 0o700)
        for leaf in self.root().iterdir():
            self.assertEqual(stat.S_IMODE(leaf.stat().st_mode), 0o600)
        probe = json.loads((self.root() / 'record-storage-probe.json').read_bytes())
        self.assertFalse(probe['power_loss_tested'])

    def test_duplicate_run_refuses_without_overwrite(self):
        if not self.available():
            return
        p = self.create()
        p.record('preserve', {'keep': 1})
        with self.assertRaisesRegex(d.Refused, 'durable-exclusive'):
            d.DurablePorts(str(self.parent), 'a' * 64, 200, clock=lambda: self.now)
        self.assertEqual(json.loads((self.root() / 'record-preserve.json').read_bytes()), {'keep': 1})

    def test_duplicate_record_is_sticky_and_preserved(self):
        if not self.available():
            return
        p = self.create()
        p.record('same', {'first': True})
        with self.assertRaisesRegex(d.Refused, 'durable-exclusive'):
            p.record('same', {'first': False})
        with self.assertRaisesRegex(d.Refused, 'durable-state'):
            p.record('later', {})
        self.assertEqual(json.loads((self.root() / 'record-same.json').read_bytes()), {'first': True})

    def test_record_name_refuses_traversal_before_create(self):
        if not self.available():
            return
        for i, name in enumerate(('../escape', '/absolute', 'x/y', 'X', '', 'a' * 97)):
            p = self.create(format(i + 1, '064x'))
            with self.assertRaisesRegex(d.Refused, 'durable-name'):
                p.record(name, {})
            p.close()
        self.assertFalse((self.parent / 'escape').exists())

    def test_record_noninteger_value_refuses_and_poisoned(self):
        if not self.available():
            return
        p = self.create()
        with self.assertRaisesRegex(d.Refused, 'durable-json'):
            p.record('bad', {'float': 1.0})
        self.assertFalse((self.root() / 'record-bad.json').exists())
        with self.assertRaisesRegex(d.Refused, 'durable-state'):
            p.record('after', {})

    def test_artifact_slot_key_c0_and_size_refusals(self):
        if not self.available():
            return
        cases = [('planner', 'source', 'x'), ('../slot', 'text', 'x'),
                 ('analysis-6', 'text', 'x'), ('builder-0', 'source', '\x00'),
                 ('planner', 'text', '\ud800'), ('planner', 'text', 'x' * 8193)]
        for i, args in enumerate(cases):
            p = self.create(format(i + 1, '064x'))
            with self.assertRaises(d.Refused):
                p.retain_artifact(*args)
            p.close()

    def test_artifact_cap_counts_utf8_bytes_and_no_newline_added(self):
        if not self.available():
            return
        p = self.create()
        text = '\u00e9' * 4096
        self.assertEqual(p.retain_artifact('planner', 'text', text), hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual((self.root() / 'artifact-planner-text.txt').stat().st_size, 8192)

    def test_private_parent_mode_required(self):
        if not self.available():
            return
        self.parent.chmod(0o755)
        with self.assertRaisesRegex(d.Refused, 'durable-parent-mode'):
            self.create()
        self.parent.chmod(0o700)

    def test_group_writable_ancestor_refused(self):
        if not self.available():
            return
        child = self.parent / 'child'; child.mkdir(mode=0o700)
        self.parent.chmod(0o770)
        try:
            with self.assertRaisesRegex(d.Refused, 'durable-ancestor'):
                d.DurablePorts(str(child), 'a' * 64, 200, clock=lambda: self.now)
        finally:
            self.parent.chmod(0o700)

    def test_symlink_parent_and_leaf_refuse(self):
        if not self.available():
            return
        target = self.parent / 'real'; target.mkdir(mode=0o700)
        link = self.parent / 'link'; link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(d.Refused, 'durable-path'):
            d.DurablePorts(str(link), 'b' * 64, 200, clock=lambda: self.now)
        p = self.create()
        leaf = self.root() / 'record-linked.json'
        leaf.symlink_to(target / 'never')
        with self.assertRaisesRegex(d.Refused, 'durable-exclusive'):
            p.record('linked', {})
        self.assertFalse((target / 'never').exists())

    def test_named_parent_replacement_refuses(self):
        if not self.available():
            return
        p = self.create()
        moved = self.parent.with_name(self.parent.name + '-moved')
        self.parent.rename(moved)
        self.parent.mkdir(mode=0o700)
        try:
            with self.assertRaisesRegex(d.Refused, 'durable-path-rebound'):
                p.record('after', {})
        finally:
            self.parent.rmdir()
            moved.rename(self.parent)

    def test_run_mode_drift_refuses(self):
        if not self.available():
            return
        p = self.create()
        self.root().chmod(0o755)
        with self.assertRaisesRegex(d.Refused, 'durable-path-rebound'):
            p.record('after', {})

    def test_hardlinked_file_readback_refuses(self):
        if not self.available():
            return
        p = self.create()
        original = d.full_sync
        linked = False
        def sync(fd, kind):
            nonlocal linked
            original(fd, kind)
            if kind == 'file' and not linked:
                os.link(self.root() / 'record-linked.json', self.root() / 'other-link')
                linked = True
        with patch.object(d, 'full_sync', side_effect=sync), self.assertRaisesRegex(d.Refused, 'durable-file'):
            p.record('linked', {})

    def test_short_write_preserves_partial_and_stops(self):
        if not self.available():
            return
        p = self.create(); original = os.write
        with patch.object(d.os, 'write', side_effect=lambda fd, raw: original(fd, raw[:1])):
            with self.assertRaisesRegex(d.Refused, 'durable-short-write'):
                p.record('short', {'x': 1})
        self.assertEqual((self.root() / 'record-short.json').stat().st_size, 1)
        with self.assertRaisesRegex(d.Refused, 'durable-state'):
            p.record('next', {})

    def test_readback_corruption_refuses(self):
        if not self.available():
            return
        p = self.create()
        with patch.object(d.os, 'read', side_effect=[b'?', b'']), self.assertRaisesRegex(d.Refused, 'durable-readback'):
            p.record('corrupt', {})

    def test_fullsync_failure_records_kind_and_errno(self):
        if not self.available():
            return
        p = self.create()
        fault = d.Refused('durable-full-sync', 'directory', errno.EIO)
        with patch.object(d, 'full_sync', side_effect=fault), self.assertRaises(d.Refused) as caught:
            p.record('sync-fault', {})
        self.assertIs(caught.exception, fault)
        self.assertTrue((self.root() / 'record-sync-fault.json').exists())

    def test_interrupt_propagates_original_and_closes(self):
        if not self.available():
            return
        for i, error in enumerate((KeyboardInterrupt(), SystemExit(8))):
            p = self.create(format(i + 1, '064x'))
            with patch.object(d.os, 'write', side_effect=error), self.assertRaises(type(error)) as caught:
                p.record('interrupted', {})
            self.assertIs(caught.exception, error)
            self.assertIsNone(p._run_fd)
            with self.assertRaisesRegex(d.Refused, 'durable-state'):
                p.record('after', {})

    def test_cleanup_error_does_not_replace_original(self):
        if not self.available():
            return
        p = self.create(); error = KeyboardInterrupt()
        original = os.close
        def close(fd):
            original(fd)
            raise OSError(errno.EIO, 'private diagnostic')
        with patch.object(d.os, 'write', side_effect=error), patch.object(d.os, 'close', side_effect=close):
            with self.assertRaises(KeyboardInterrupt) as caught:
                p.record('interrupted', {})
        self.assertIs(caught.exception, error)

    def test_file_count_and_total_byte_caps(self):
        if not self.available():
            return
        for i, attr, value in ((1, '_files', d.FILE_COUNT), (2, '_bytes', d.TOTAL_BYTES)):
            p = self.create(format(i, '064x')); setattr(p, attr, value)
            with self.assertRaisesRegex(d.Refused, 'durable-cap'):
                p.record('full', {})
            p.close()

    def test_deadline_and_clock_regression_refuse(self):
        if not self.available():
            return
        p = self.create(); self.now = 200
        with self.assertRaisesRegex(d.Refused, 'durable-deadline'):
            p.record('late', {})
        self.now = 100; p = self.create('b' * 64); self.now = 99
        with self.assertRaisesRegex(d.Refused, 'durable-clock'):
            p.record('regression', {})

    def test_late_sync_return_refuses_after_retained_write(self):
        if not self.available():
            return
        p = self.create(); original = d.full_sync
        def late(fd, kind):
            original(fd, kind); self.now = 201
        with patch.object(d, 'full_sync', side_effect=late), self.assertRaisesRegex(d.Refused, 'durable-deadline'):
            p.record('late', {})
        self.assertTrue((self.root() / 'record-late.json').exists())

    def test_close_and_process_identity_block_further_records(self):
        if not self.available():
            return
        p = self.create(); p.close()
        with self.assertRaisesRegex(d.Refused, 'durable-state'):
            p.record('closed', {})
        p = self.create('b' * 64)
        with patch.object(d.os, 'getpid', return_value=p._pid + 1), self.assertRaisesRegex(d.Refused, 'durable-state'):
            p.record('other-process', {})


if __name__ == '__main__':
    unittest.main()
