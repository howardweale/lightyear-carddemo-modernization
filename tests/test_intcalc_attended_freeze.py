"""Synthetic admission/joins only. No verifier archive or real oracle imports."""
import ast
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import contextlib
import io
import unittest
from unittest.mock import Mock, patch
from tools import intcalc_attended_freeze as m
from tools import qualify_intcalc_attended_freeze as qualification


def receipt():
    return dict(schema='c2-attended-freeze-equivalence/2', source_commit='a' * 40, source_tree='b' * 40,
                source_event='push', source_ref='refs/heads/main',
                bundle_sha256=m.BUNDLE_HASH, controller_sha256='c' * 64, entry_sha256='d' * 64,
                case_manifest_sha256='e' * 64, outputs_sha256='f' * 64, equal=True,
                candidate_executed=False, model_calls=0)


class AttendedFreezeTests(unittest.TestCase):
    def test_generated_tail_keeps_token_last_after_private_traceback(self):
        core=('import os\ndef prepare(root, destination):\n'+m.GUARD+'    return True\n').encode()
        with patch.object(m,'CORE_HASH',m.sha(core)):
            entry=m.build_entry(core,Path(m.__file__).read_bytes())
        tail=ast.parse(entry).body[-1]
        self.assertIsInstance(tail,ast.Try)
        worker=Mock(side_effect=RuntimeError('synthetic-private-detail'))
        scope=dict(worker=worker,Refused=m.Refused,public_code=m.public_code,
                   child_refusal=m.child_refusal,traceback=m.traceback,sys=m.sys)
        private_log=io.StringIO()
        with contextlib.redirect_stderr(private_log):
            with self.assertRaises(SystemExit):
                exec(compile(ast.Module(body=[tail],type_ignores=[]),'<synthetic-entry-tail>','exec'),scope)
        raw=private_log.getvalue()
        self.assertIn('Traceback (most recent call last):',raw)
        self.assertIn('synthetic-private-detail',raw)
        self.assertEqual(raw.splitlines()[-1],'C2_FREEZE_REFUSED:freeze-child-fault')
        with tempfile.TemporaryFile() as stream:
            stream.write(raw.encode());stream.flush()
            self.assertEqual(m.read_child_refusal(stream.fileno(),0),'freeze-child-fault')

    def test_unexpected_parent_fault_is_private_and_preserved(self):
        terminal=io.StringIO()
        if os.name != 'posix':
            with contextlib.redirect_stderr(terminal),self.assertRaisesRegex(RuntimeError,'synthetic-private-detail'):
                with m.private_parent_diagnosis(Path('unused')):
                    raise RuntimeError('synthetic-private-detail')
            self.assertEqual(terminal.getvalue(),'')
            return
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();root.chmod(0o700)
            with contextlib.redirect_stderr(terminal),self.assertRaisesRegex(RuntimeError,'synthetic-private-detail'):
                with m.private_parent_diagnosis(root):
                    raise RuntimeError('synthetic-private-detail')
            raw=(root/'parent-private.log').read_text()
            self.assertIn('Traceback (most recent call last):',raw)
            self.assertIn('synthetic-private-detail',raw)
            self.assertEqual((root/'parent-private.log').stat().st_mode & 0o777,0o600)
            self.assertEqual(terminal.getvalue(),'')

    def test_public_code_rejects_arbitrary_message(self):
        self.assertEqual(m.public_code(m.Refused('source-tree'),'freeze-exit'),'source-tree')
        self.assertEqual(m.public_code(m.Refused('private/path value'),'freeze-exit'),'freeze-exit')

    def test_child_token_exact_and_unknown_fallback(self):
        for tail, expected in ((b'C2_FREEZE_REFUSED:source-tree\n','source-tree'),
                               (b'C2_FREEZE_REFUSED:unknown/private\n','freeze-exit'),
                               (b'C2_FREEZE_REFUSED:source-tree','freeze-exit'),
                               (b'C2_FREEZE_REFUSED:\xff\n','freeze-exit'),
                               (b'not-a-token\n','freeze-exit')):
            with tempfile.TemporaryFile() as stream:
                stream.write(b'private log prefix\n'+tail);stream.flush()
                self.assertEqual(m.read_child_refusal(stream.fileno(),19),expected)

    def test_old_segment_token_cannot_be_used(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(b'C2_FREEZE_REFUSED:source-tree\n');stream.flush()
            self.assertEqual(m.read_child_refusal(stream.fileno(),stream.tell()),'freeze-exit')

    def test_child_refusal_prints_only_allowlisted_token(self):
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit):m.child_refusal('private/path value')
        self.assertEqual(output.getvalue(),'C2_FREEZE_REFUSED:freeze-child-fault\n')

    def test_mac_rejects_pull_request_receipt(self):
        row=receipt();row.update(source_event='pull_request',source_ref='refs/pull/1/merge')
        self.assertEqual(m.validate_receipt(row,require_main=False),row)
        with self.assertRaisesRegex(m.Refused,'receipt-origin'):m.validate_receipt(row)

    def test_mac_rejects_non_main_push_receipt(self):
        row=receipt();row['source_ref']='refs/heads/other'
        with self.assertRaisesRegex(m.Refused,'receipt-origin'):m.validate_receipt(row)

    def test_source_only_ci_mode_returns_before_bundle_or_writes(self):
        output=io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            args=['qualification','--source',str(Path(tmp).resolve()),'--source-admission-only']
            with patch.dict(m.os.environ,{'GITHUB_ACTIONS':'true'}),patch.object(qualification.sys,'argv',args),patch.object(m,'git',side_effect=[b'a'*40,b'b'*40]),patch.object(m,'source_admission') as admission,patch.object(m,'bundle_files') as bundle,patch.object(m,'exclusive') as write,contextlib.redirect_stdout(output):
                qualification.main()
                admission.assert_called_once();bundle.assert_not_called();write.assert_not_called()
        self.assertEqual(output.getvalue(),'source-admission-match\n')

    def test_python_floor(self):
        with patch.object(m.sys, 'version_info', (3, 10)):
            with self.assertRaisesRegex(m.Refused, 'python-version'): m.posix()

    def test_receipt_accepts_exact_fields(self):
        self.assertEqual(m.validate_receipt(receipt()), receipt())

    def test_receipt_rejects_missing_and_extra(self):
        for key in receipt():
            value = receipt(); del value[key]
            with self.assertRaises(m.Refused): m.validate_receipt(value)
        value = receipt(); value['private_path'] = 'redacted'
        with self.assertRaises(m.Refused): m.validate_receipt(value)

    def test_receipt_rejects_wrong_bundle(self):
        value = receipt(); value['bundle_sha256'] = 'a' * 64
        with self.assertRaisesRegex(m.Refused, 'receipt-result'): m.validate_receipt(value)

    def test_receipt_rejects_failed_equivalence(self):
        value = receipt(); value['equal'] = False
        with self.assertRaisesRegex(m.Refused, 'receipt-result'): m.validate_receipt(value)

    def test_receipt_rejects_execution(self):
        for key, val in (('candidate_executed', True), ('model_calls', 1), ('model_calls', False)):
            value = receipt(); value[key] = val
            with self.assertRaises(m.Refused): m.validate_receipt(value)

    def test_receipt_rejects_nonhashes(self):
        for key in ('source_commit', 'source_tree', 'controller_sha256', 'entry_sha256', 'case_manifest_sha256'):
            value = receipt(); value[key] = None
            with self.assertRaises(m.Refused): m.validate_receipt(value)

    def test_strict_utf8(self):
        with self.assertRaises(m.Refused): m.strict_json('{}' .encode('utf-16'))

    def test_duplicate_keys(self):
        with self.assertRaisesRegex(m.Refused, 'json-duplicate'): m.strict_json(b'{"a":1,"a":2}')

    def test_float_and_nonfinite_refused(self):
        for raw in (b'1.0', b'1e400', b'NaN', b'Infinity'):
            with self.assertRaisesRegex(m.Refused, 'json-number'): m.strict_json(raw)

    def test_non_posix_before_uid(self):
        with patch.object(m.os, 'name', 'nt'), patch.object(m.os, 'getuid', create=True) as uid:
            with self.assertRaisesRegex(m.Refused, 'platform'): m.posix()
            uid.assert_not_called()

    def test_root_account_refused(self):
        with patch.object(m.os, 'name', 'posix'), patch.object(m.os, 'getuid', return_value=0, create=True):
            with self.assertRaisesRegex(m.Refused, 'standard-account'): m.posix()

    def test_core_delta_is_only_guard(self):
        raw = ('import os\ndef prepare(root, destination):\n' + m.GUARD + '    return True\n').encode()
        with patch.object(m, 'CORE_HASH', m.sha(raw)):
            result = m.core_text(raw)
            self.assertNotIn(m.GUARD, result)
            self.assertIn('return True', result)
            ast.parse(result)

    def test_core_wrong_hash(self):
        with self.assertRaisesRegex(m.Refused, 'core-hash'): m.core_text(b'not the pinned core')

    def test_core_guard_shape(self):
        raw = b'def prepare(a,b):\n    return True\n'
        with patch.object(m, 'CORE_HASH', m.sha(raw)):
            with self.assertRaisesRegex(m.Refused, 'core-guard-shape'): m.core_text(raw)

    def test_core_duplicate_guard(self):
        raw = ('def prepare(a,b):\n' + m.GUARD + m.GUARD).encode()
        with patch.object(m, 'CORE_HASH', m.sha(raw)):
            with self.assertRaisesRegex(m.Refused, 'core-guard-shape'): m.core_text(raw)

    def test_build_asset_is_deterministic(self):
        raw = ('import os\ndef prepare(a,b):\n' + m.GUARD + '    return True\n').encode()
        public = b'def worker(text): pass\n\n# PUBLIC_COMMAND_ENTRY\npass\n'
        with patch.object(m, 'CORE_HASH', m.sha(raw)):
            first = m.build_entry(raw, public)
            self.assertEqual(first, m.build_entry(raw, public))
            ast.parse(first)

    def test_build_asset_requires_command_boundary(self):
        with self.assertRaisesRegex(m.Refused, 'controller-shape'): m.build_entry(b'', b'pass\n')

    def test_manifest_mismatch_prevents_binding_write(self):
        with patch.object(m, 'read_file', return_value=b'wrong'), patch.object(m, 'exclusive') as write:
            with self.assertRaisesRegex(m.Refused, 'manifest-mismatch'):
                m.bind(Path('out'), Path('run'), Path('template'), 'a' * 64, receipt())
            write.assert_not_called()

    def test_template_hash_refused_before_write(self):
        value = receipt(); value['case_manifest_sha256'] = m.sha(b'manifest')
        with patch.object(m, 'read_file', side_effect=[b'manifest', b'template']), patch.object(m, 'exclusive') as write:
            with self.assertRaisesRegex(m.Refused, 'template-hash'):
                m.bind(Path('out'), Path('run'), Path('template'), 'a' * 64, value)
            write.assert_not_called()

    def test_binding_machine_hash_and_strict_policy(self):
        value = receipt(); value['case_manifest_sha256'] = m.sha(b'manifest')
        template = m.canonical(dict(schema='full-intcalc-c1/2', runtime_platform='linux/arm64', artifact={'path':None,'sha256':None}))
        with patch.object(m, 'read_file', side_effect=[b'manifest', template]), patch.object(m, 'exclusive') as write:
            m.bind(Path('out'), Path('run'), Path('template'), m.sha(template), value)
            result = m.strict_json(write.call_args.args[1])
            self.assertEqual(result['case_manifest']['sha256'], value['case_manifest_sha256'])
            self.assertNotIn('byte_policy', result)

    def test_source_commit_refused(self):
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', return_value=b'wrong'):
            with self.assertRaisesRegex(m.Refused, 'source-commit'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_source_tree_refused(self):
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', side_effect=[b'a'*40,b'wrong']):
            with self.assertRaisesRegex(m.Refused, 'source-tree'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_dirty_source_refused(self):
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', side_effect=[b'a'*40,b'b'*40,b'M file']):
            with self.assertRaisesRegex(m.Refused, 'source-dirty'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_ignored_shadow_refused(self):
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', side_effect=[b'a'*40,b'b'*40,b'',b'src/shadow.py']):
            with self.assertRaisesRegex(m.Refused, 'source-untracked'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_tracked_source_bytes_must_match_git_blob(self):
        tree = b'100644 blob ' + b'c'*40 + b'\tsrc/synthetic.py\0'
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', side_effect=[b'a'*40,b'b'*40,b'',b'',tree]), patch.object(m, 'read_file', return_value=b'changed'):
            with self.assertRaisesRegex(m.Refused, 'source-bytes'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_source_rejects_symlink_blob(self):
        tree = b'120000 blob ' + b'c'*40 + b'\tsrc/synthetic.py\0'
        with patch.object(m, 'checked_path', return_value=Path('source')), patch.object(m, 'git', side_effect=[b'a'*40,b'b'*40,b'',b'',tree]):
            with self.assertRaisesRegex(m.Refused, 'source-kind'): m.source_admission('source', 'a'*40, 'b'*40)

    def test_template_optional_policy_refused(self):
        value = receipt(); value['case_manifest_sha256'] = m.sha(b'manifest')
        template = m.canonical(dict(schema='full-intcalc-c1/2', runtime_platform='linux/arm64', artifact={'path':None,'sha256':None}, byte_policy={}))
        with patch.object(m, 'read_file', side_effect=[b'manifest', template]), patch.object(m, 'exclusive') as write:
            with self.assertRaisesRegex(m.Refused, 'template-schema'): m.bind(Path('out'),Path('run'),Path('template'),m.sha(template),value)
            write.assert_not_called()

    def test_child_nonzero_fixed_failure(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.child(Path('entry'),{},7)
            return
        proc = Mock(returncode=2); proc.poll.return_value=2
        with patch.object(m.subprocess, 'Popen', return_value=proc), patch.object(m.os, 'killpg', create=True) as kill,patch.object(m,'log_end',return_value=0),patch.object(m,'read_child_refusal',return_value='freeze-exit'):
            with self.assertRaisesRegex(m.Refused, 'freeze-exit'): m.child(Path('entry'), {}, 7)
            kill.assert_not_called()

    def test_child_timeout_killed_and_reaped(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.child(Path('entry'),{},7)
            return
        proc=Mock(pid=123);proc.poll.return_value=None
        proc.communicate.side_effect=subprocess.TimeoutExpired('synthetic',1)
        with patch.object(m.subprocess,'Popen',return_value=proc), patch.object(m.os,'killpg',create=True) as kill,patch.object(m,'log_end',return_value=0):
            with self.assertRaises(subprocess.TimeoutExpired): m.child(Path('entry'),{},7)
            kill.assert_called_once_with(123,m.signal.SIGKILL);proc.wait.assert_called_once_with(timeout=5)

    def test_child_interrupt_preserved_and_reaped(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.child(Path('entry'),{},7)
            return
        proc=Mock(pid=123);proc.poll.return_value=None;proc.communicate.side_effect=KeyboardInterrupt
        with patch.object(m.subprocess,'Popen',return_value=proc),patch.object(m.os,'killpg',create=True),patch.object(m,'log_end',return_value=0):
            with self.assertRaises(KeyboardInterrupt):m.child(Path('entry'),{},7)
            proc.wait.assert_called_once_with(timeout=5)

    def test_child_has_no_ci_environment_and_private_streams(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.child(Path('entry'),{},7)
            return
        proc=Mock(returncode=0);proc.poll.return_value=0
        with patch.object(m.subprocess,'Popen',return_value=proc) as launch,patch.object(m,'log_end',return_value=0):
            m.child(Path('entry'),{},7)
            self.assertEqual(launch.call_args.kwargs['stdout'],7)
            self.assertEqual(launch.call_args.kwargs['stderr'],7)
            self.assertNotIn('GITHUB_ACTIONS',launch.call_args.kwargs['env'])
            self.assertNotIn('CI',launch.call_args.kwargs['env'])

    def test_child_fixed_code_surfaces_to_parent(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.child(Path('entry'),{},7)
            return
        proc=Mock(returncode=2);proc.poll.return_value=2
        with patch.object(m.subprocess,'Popen',return_value=proc),patch.object(m,'log_end',return_value=0),patch.object(m,'read_child_refusal',return_value='source-tree'):
            with self.assertRaisesRegex(m.Refused,'source-tree'):m.child(Path('entry'),{},7)

    def test_terminal_check_is_in_parent_before_source_read(self):
        with patch.object(m,'posix'),patch.object(m.sys,'platform','darwin'),patch.object(m.platform,'machine',return_value='arm64'),patch.object(m.sys,'flags',Mock(isolated=1)),patch.object(m.sys,'dont_write_bytecode',True),patch.object(m.sys.stdin,'isatty',return_value=False),patch.object(m,'read_file') as read:
            with self.assertRaisesRegex(m.Refused,'operator-terminal'):m.attended(Mock())
            read.assert_not_called()

    def test_exclusive_output_never_overwrites(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.exclusive(Path('unused'),b'new')
            return
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();root.chmod(0o700);p=root/'record'
            m.exclusive(p,b'original')
            with self.assertRaises(FileExistsError):m.exclusive(p,b'new')
            self.assertEqual(p.read_bytes(),b'original')

    def test_symlink_path_refused(self):
        if os.name != 'posix':
            with self.assertRaisesRegex(m.Refused,'platform'):m.checked_path('unused')
            return
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();target=root/'target';target.write_bytes(b'x');link=root/'link';link.symlink_to(target)
            with self.assertRaisesRegex(m.Refused,'path-symlink'):m.checked_path(str(link))


if __name__ == '__main__':
    unittest.main()
