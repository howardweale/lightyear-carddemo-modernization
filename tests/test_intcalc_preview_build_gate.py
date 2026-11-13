"""Synthetic CI only: no Docker, candidate, provider, or verifier case reads."""
import io
import os
from pathlib import Path
import tarfile
import tempfile
import time
import sys
import unittest
from unittest.mock import patch

from lightyear_factory import intcalc_preview_build_gate as b
from lightyear_factory import intcalc_preview_composition as c
from lightyear_mainframe import intcalc_candidate_gate as g


def archive(entries):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w') as out:
        for name, kind, data in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(data)
            out.addfile(item, io.BytesIO(data))
    return result.getvalue()


class BuildGateTests(unittest.TestCase):
    def test_real_capture_normal_frame_ci_only(self):
        if os.name != 'posix':
            with self.assertRaises(b.AdapterRefused):
                b.capture([], 1, 2)
            return
        start = time.monotonic()
        result = b.capture([sys.executable, '-I', '-c', 'print("synthetic")'], start + 15, start + 17)
        self.assertEqual(result['rc'], 0)
        self.assertEqual(result['stdout'].strip(), b'synthetic')

    def test_real_capture_stall_reaped_ci_only(self):
        if os.name != 'posix':
            with self.assertRaises(b.AdapterRefused):
                b.capture([], 1, 2)
            return
        start = time.monotonic()
        with self.assertRaises(b.AdapterRefused):
            b.capture([sys.executable, '-I', '-c', 'import time; time.sleep(20)'], start + 1, start + 4)
        self.assertLess(time.monotonic() - start, 4)

    def test_single_jar(self):
        self.assertEqual(b.jar_from_tar(archive([('candidate.jar', tarfile.REGTYPE, b'jar')])), b'jar')

    def test_archive_names_links_duplicates_and_empty(self):
        cases = [[], [('other', tarfile.REGTYPE, b'x')], [('../candidate.jar', tarfile.REGTYPE, b'x')],
                 [('/candidate.jar', tarfile.REGTYPE, b'x')], [('candidate.jar', tarfile.SYMTYPE, b'')],
                 [('candidate.jar', tarfile.DIRTYPE, b'')], [('candidate.jar', tarfile.REGTYPE, b'')],
                 [('candidate.jar', tarfile.REGTYPE, b'x')] * 2]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(b.AdapterRefused):
                b.jar_from_tar(archive(rows))

    def test_archive_garbage(self):
        with self.assertRaises(b.AdapterRefused):
            b.jar_from_tar(b'invalid')

    def test_phase_uses_earlier_original_end(self):
        self.assertEqual(b.phase(c.PhaseWindow(110, 100), clock=lambda: 50), (70, 100))

    def test_phase_refuses_late_nonfinite_and_cleanup_change(self):
        for window in (c.PhaseWindow(100, 100), c.PhaseWindow(float('nan'), 100), c.PhaseWindow(200, 200, 6)):
            with self.assertRaises(b.AdapterRefused):
                b.phase(window, clock=lambda: 96)

    def test_resource_names_are_not_commands(self):
        self.assertTrue(b.resource_name('volume', 'c2-build-' + 'a' * 32 + '-out'))
        for value in ('other', '../x', '--all', 'c2-build-' + 'a' * 31):
            self.assertFalse(b.resource_name('container', value))

    def test_registry_immutable_and_removal_join(self):
        if os.name != 'posix':
            with self.assertRaises(b.AdapterRefused):
                b.Registry('.')
            return
        with tempfile.TemporaryDirectory() as tmp, patch.object(b, 'persist'):
            root = Path(tmp).resolve()
            root.chmod(0o700)
            registry = b.Registry(root)
            name = 'c2-build-' + 'a' * 32
            registry.register('container', name)
            with self.assertRaises(FileExistsError):
                registry.register('container', name)
            self.assertEqual(len(registry.entries()), 1)
            registry.removed('container', name)
            self.assertEqual(registry.entries(), [])

    def test_symlink_path_refused(self):
        if os.name != 'posix':
            with self.assertRaises(b.AdapterRefused):
                b.safe_path('.')
            return
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'file').write_bytes(b'x')
            (root / 'link').symlink_to(root / 'file')
            with self.assertRaises(b.AdapterRefused):
                b.read_file(root / 'link', 10)

    def test_nonposix_before_os_flags(self):
        with patch.object(b.os, 'name', 'nt'):
            with self.assertRaises(b.AdapterRefused):
                b.capture([], 1, 2)

    def test_controller_refuses_other_platform_before_effects(self):
        with patch.object(b.sys, 'platform', 'linux'), patch.object(b.subprocess, 'Popen') as spawn:
            with self.assertRaises(b.AdapterRefused):
                b.BuildGateAdapter({}, parent='.', session_id='a' * 64, docker_binary='x', endpoint='unix:///x',
                                   verifier_binding='x', verifier_binding_sha256='a' * 64, gate_source_sha256='a' * 64)
            spawn.assert_not_called()

    def test_cleanup_requires_absence_not_cli_exit_alone(self):
        class Registry:
            def entries(self):
                return [{'kind': 'container', 'name': 'c2-build-' + 'a' * 32}]
            def removed(self, *args):
                raise AssertionError('must not mark removed')
        with patch.object(b, 'capture', return_value={'rc': 0, 'stdout': b'[]', 'stderr': b''}):
            with self.assertRaises(b.AdapterRefused):
                b.cleanup(['docker'], Registry(), time.monotonic() + 5)

    def test_absolute_gate_context_is_reset(self):
        if os.name != 'posix':
            with self.assertRaises(g.Refused):
                g.run('x', 'x', 'x', absolute_deadline=time.monotonic() + 30,
                      docker_prefix=['/docker', '--config', '/config', '--host', 'unix:///endpoint'],
                      resource_register=lambda *args: None, cleanup_seconds=18)
            return
        prefix = ['/docker', '--config', '/config', '--host', 'unix:///endpoint']
        with patch.object(g.os, 'name', 'posix'), patch.object(g, '_run', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                g.run('x', 'x', 'x', absolute_deadline=time.monotonic() + 30,
                      docker_prefix=prefix, resource_register=lambda *args: None, cleanup_seconds=18)
        self.assertIsNone(g._C2_CONTEXT.get())

    def test_absolute_gate_requires_complete_context(self):
        with self.assertRaises(g.Refused):
            g.run('x', 'x', 'x', docker_prefix=[])
        with self.assertRaises(g.Refused):
            g.run('x', 'x', 'x', absolute_deadline=time.monotonic() + 20, docker_prefix=[], resource_register=None)

    def test_legacy_gate_dispatch_unchanged(self):
        with patch.object(g, '_run', return_value={'synthetic': True}) as call:
            self.assertEqual(g.run('a', 'b', 'c'), {'synthetic': True})
            call.assert_called_once_with('a', 'b', 'c')

    def test_absolute_capture_only_fixed_docker_prefix(self):
        token = g._C2_CONTEXT.set((100, ('/fixed/docker',), lambda *args: None, 18))
        try:
            with self.assertRaises(g.Refused):
                g.capture(['sh', '-c', 'anything'], 90)
            with patch.object(g, 'absolute_capture', return_value={}) as call:
                g.capture(['docker', 'info'], 90)
                self.assertEqual(call.call_args.args[:3], (['/fixed/docker', 'info'], 90, 100))
        finally:
            g._C2_CONTEXT.reset(token)


if __name__ == '__main__':
    unittest.main()
