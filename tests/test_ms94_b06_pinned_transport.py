"""Synthetic admission mutants; host network/exec evidence is never synthesized."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, digest
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_pinned_transport import ARGS, PATH, SHA, FILES, validate, admit, plan


def fixture():
    sid='S-1-5-21-1-2-3-1006'
    transport={'codex_path':PATH,'codex_sha256':SHA,'account_sid':sid,'pinned_plan_sha256':'a'*64}
    binding={'path':'process.json','sha256':'b'*64}
    body={'artifact_type':'ms94-b06-pinned-transport-proof/1','status':'passed',
        'codex_path':PATH,'codex_sha256':SHA,'account_sid_sha256':digest(sid),
        'process_probe_sha256':binding['sha256'],'plan_sha256':'a'*64,
        'exec':{'arguments':ARGS,'stdin_bytes':0,'stdout_bytes':0,'model_calls':0,'prompt_sent':False,
            'exit_code':1,'missing_prompt_rejected':True,'codex_path':PATH,'codex_sha256':SHA,'account_sid':sid},
        'wfp_verified':True,'wfp_filters_removed':True,'account_disabled':True,'temporary_codex_block_removed':True,
        'network_probes':[{'address':address,'identity_sid':sid,'error':10013,'connected':False,
            'host_positive_connected':True} for address in ('127.0.0.1','::1')]}
    return body,transport,binding


class PinnedTransportTests(unittest.TestCase):
    def test_eof_identity_fixed_path_both_families_and_cleanup_mutants(self):
        body,transport,binding=fixture();validate(body,transport,binding)
        for field,value in [('codex_path','C:/desktop/codex.exe'),('codex_sha256','c'*64),
            ('account_sid_sha256','d'*64),('process_probe_sha256','e'*64),('wfp_verified',False),
            ('wfp_filters_removed',False),('account_disabled',False),('temporary_codex_block_removed',False),
            ('network_probes',body['network_probes'][:1])]:
            with self.subTest(field=field),self.assertRaises(ValueError):validate({**body,field:value},transport,binding)
        for field,value in [('arguments','exec --help'),('stdin_bytes',1),('stdout_bytes',1),
            ('model_calls',1),('exit_code',0),('exit_code',2),('prompt_sent',True),('account_sid','other')]:
            bad=copy.deepcopy(body);bad['exec'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate(bad,transport,binding)
        for field,value in [('connected',True),('error',10061),('host_positive_connected',False),('identity_sid','other')]:
            bad=copy.deepcopy(body);bad['network_probes'][1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate(bad,transport,binding)

    def test_signed_file_hash_code_plan_and_binary_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tools').mkdir()
            for name in FILES:(root/name).write_bytes(b'unit-fixture')
            body,transport,binding=fixture();signer=test_signer()
            spec=plan(root,transport['account_sid'])
            self.assertEqual(PATH,spec['codex_path']);self.assertFalse(spec['model_calls_authorized'])
            body['implementation_sha256']=spec['implementation_sha256']
            def write(value):
                (root/'proof.json').write_bytes(canonical(signer.sign(value)))
                transport['pinned_probe']={'path':'proof.json','sha256':file_hash(root/'proof.json')}
            real=file_hash
            with patch('tools.ms94_b06_pinned_transport.file_hash',side_effect=lambda p:SHA if str(p)==str(Path(PATH)) else real(p)):
                write(body);self.assertEqual('passed',admit(root,transport,signer.public,binding)['status'])
                transport['pinned_plan_sha256']='c'*64
                with self.assertRaisesRegex(ValueError,'plan-differs'):admit(root,transport,signer.public,binding)
                transport['pinned_plan_sha256']='a'*64
                write({**body,'implementation_sha256':{}})
                with self.assertRaisesRegex(ValueError,'binding-incomplete'):admit(root,transport,signer.public,binding)
                write(body);(root/FILES[0]).write_bytes(b'tampered')
                with self.assertRaises(ValueError):admit(root,transport,signer.public,binding)

    @unittest.skipUnless(sys.platform=='win32','Windows parser/compiler checks')
    def test_real_start_info_arguments_match_the_bound_exec_plan(self):
        root=Path(__file__).resolve().parents[1]
        command=r"""$ErrorActionPreference='Stop'
. ./tools/ms94_b06_pinned_exec.ps1
# Import before mocking: New-Object may otherwise autoload Utility and replace the mock.
Import-Module Microsoft.PowerShell.Utility
$script:hashReads=0
function Get-FileHash { param($LiteralPath,$Algorithm);$script:hashReads++;return @{Hash='4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01'} }
$secret=New-Object Security.SecureString
$secret.AppendChar('x')
$credential=New-Object Management.Automation.PSCredential('unit-no-launch',$secret)
$policy=@{codex_path='C:\Program Files\Lightyear\Codex\0.160.0\codex.exe';codex_sha256='4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01'}
$info=New-B06PinnedExecStartInfo -Policy $policy -Credential $credential -WorkingDirectory (Get-Location).Path -CodexHome (Join-Path $env:TEMP 'unit-no-launch')
if ($script:hashReads -ne 1) { throw 'Unit hash boundary was not exercised' }
$info.Arguments
$credential.Password.Dispose()
"""
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual(ARGS,result.stdout.strip())
        self.assertTrue(ARGS.startswith('exec --ignore-user-config '))

    @unittest.skipUnless(sys.platform=='win32','Windows parser/compiler checks')
    def test_eof_helper_reaches_process_construction_without_assigning_home(self):
        root=Path(__file__).resolve().parents[1]
        # Run the real helper under Windows PowerShell, where HOME is read-only.
        # Stop at the process-construction boundary: no executable can start.
        command=r"""$ErrorActionPreference='Stop'
. ./tools/ms94_b06_pinned_exec.ps1
$originalHome=$HOME
$script:reachedConstruction=$false
function New-B06PinnedExecStartInfo {
param($Policy,$Credential,$WorkingDirectory,$CodexHome)
if ($CodexHome -ne (Join-Path $env:TEMP 'b06-unit-eof-no-launch/exec-home')) { throw 'Wrong isolated home' }
$script:reachedConstruction=$true
throw 'intentional-unit-prelaunch-boundary'
}
try {
Invoke-B06PinnedExecEof -Policy @{} -Directory (Get-Location).Path -Results (Join-Path $env:TEMP 'b06-unit-eof-no-launch')
throw 'Unit boundary was skipped'
} catch {
if ($_.Exception.Message -ne 'intentional-unit-prelaunch-boundary') { throw }
}
if (!$script:reachedConstruction -or $HOME -ne $originalHome) { throw 'Protected HOME was touched' }
exit 0
"""
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)

    @unittest.skipUnless(sys.platform=='win32','Windows parser/compiler checks')
    def test_real_powershell_parser_and_wfp_struct_layout(self):
        root=Path(__file__).resolve().parents[1]
        command="""$ErrorActionPreference='Stop';foreach($f in @('tools/ms94_b06_pinned_exec.ps1','tools/ms94_b06_pinned_probe.ps1')){$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f),[ref]$t,[ref]$e)|Out-Null;if($e){throw ($e|Out-String)}};Add-Type -Path tools/b06-account-egress.cs;if(([B06AccountEgress]::LayoutSizes() -join ',') -ne '16,40,200,72'){throw 'WFP SDK layout mismatch'}"""
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)


if __name__=='__main__':unittest.main()
