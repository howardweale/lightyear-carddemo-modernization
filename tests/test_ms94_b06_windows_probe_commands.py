"""Run the real short commands on public temp files; not a denial attestation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'built-in Windows PowerShell required')
class ShortProbeCommands(unittest.TestCase):
    def test_real_commands_fit_credentialed_limit_and_distinguish_missing_file(self):
        runtime=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        root=Path(__file__).resolve().parents[1]
        factory=root/'tools/ms94_b06_windows_probe_commands.ps1'
        query=". '"+str(factory).replace("'","''")+"'; @(Get-B06ProbeCommands) | ConvertTo-Json"
        response=subprocess.run([str(runtime),'-NoProfile','-NonInteractive','-Command',query],
                                check=True,capture_output=True,timeout=15)
        commands=json.loads(response.stdout)
        self.assertEqual(len(commands),5)
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary); target=directory/'allowed.txt';target.write_text('public fixture')
            policy={'results_directory':str(directory),'read_targets':[str(target)]*3+[str(directory/'missing.txt')]}
            (directory/'policy.json').write_text(json.dumps(policy),encoding='utf-8-sig')
            quote=lambda value:"'"+str(value).replace("'","''")+"'"
            for index,command in enumerate(commands):
                full='"'+str(runtime)+'" -NoProfile -NonInteractive -Command "'+command+'"'
                self.assertLessEqual(len(full)+1,1024)
                self.assertNotIn('-ExecutionPolicy',command)
                self.assertNotIn('ScriptBlock',command)
                launch=(". "+quote(factory)+"; $commands=@(Get-B06ProbeCommands); Invoke-B06ReadCommand -Runtime "+
                        quote(runtime)+" -Command $commands["+str(index)+"] -WorkingDirectory "+quote(directory)+
                        " -OutputLog "+quote(directory/f'out-{index}.log')+" -ErrorLog "+
                        quote(directory/f'err-{index}.log')+" -Index "+str(index)+" | ConvertTo-Json")
                result=subprocess.run([str(runtime),'-NoProfile','-NonInteractive','-Command',launch],
                                      cwd=directory,check=True,capture_output=True,timeout=15)
                observed=json.loads(result.stdout)
                self.assertEqual(observed['exit_code'],0)
                self.assertEqual(observed['index'],index)
            load=lambda name:json.loads((directory/name).read_text(encoding='utf-8-sig'))
            identity=load('identity.json')
            for index in range(4):
                result=load(f'read-{index}.json')
                self.assertEqual(result['identity_sid'],identity['identity_sid'])
                self.assertEqual(result['administrator'],identity['administrator'])
                self.assertEqual(result['opened'],index<3)
            self.assertEqual(result['category'],'ObjectNotFound')
            self.assertNotEqual(result['error'],5)

    def test_actual_exception_properties_distinguish_access_denied_from_missing(self):
        from tools.ms94_b06_os_probe import is_access_denied
        runtime=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        factory=Path(__file__).resolve().parents[1]/'tools/ms94_b06_windows_probe_commands.ps1'
        query=". '"+str(factory).replace("'","''")+"'; @(Get-B06ProbeCommands) | ConvertTo-Json"
        commands=json.loads(subprocess.run([str(runtime),'-NoProfile','-NonInteractive','-Command',query],
            check=True,capture_output=True,timeout=15).stdout)
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            (directory/'policy.json').write_text(json.dumps({'results_directory':str(directory)}),encoding='utf-8-sig')
            cases=[('New-Object ComponentModel.Win32Exception 5',True,5),
                   ('New-Object ComponentModel.Win32Exception 2',False,2),
                   ('New-Object UnauthorizedAccessException',True,None)]
            for expression,expected,native in cases:
                with self.subTest(expression=expression):
                    command=commands[1].replace('$null=Get-Content -Raw -ErrorAction Stop -LiteralPath $p.read_targets[0]',
                                                'throw ('+expression+')')
                    subprocess.run([str(runtime),'-NoProfile','-NonInteractive','-Command',command],
                                   cwd=directory,check=True,capture_output=True,timeout=15)
                    result=json.loads((directory/'read-0.json').read_text(encoding='utf-8-sig'))
                    self.assertEqual(is_access_denied(result),expected)
                    self.assertEqual(result['native_error'],native)
                    if native is not None:
                        self.assertEqual(result['hresult'],-2147467259)
                    if expected:
                        self.assertEqual(result['error'],5)
            # Attempt 7's PermissionDenied category and generic HRESULT cannot admit.
            self.assertFalse(is_access_denied({'opened':False,'error':16389,
                'category':'PermissionDenied','exception_type':'System.ComponentModel.Win32Exception'}))
            self.assertFalse(is_access_denied({'opened':False,'error':5,
                'category':'PermissionDenied','exception_type':'System.ComponentModel.Win32Exception'}))

    def test_redirected_process_nonzero_exit_is_preserved(self):
        runtime=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        factory=Path(__file__).resolve().parents[1]/'tools/ms94_b06_windows_probe_commands.ps1'
        quote=lambda value:"'"+str(value).replace("'","''")+"'"
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            query=(". "+quote(factory)+"; Invoke-B06ReadCommand -Runtime "+quote(runtime)+
                   " -Command 'exit 7' -WorkingDirectory "+quote(directory)+
                   " -OutputLog "+quote(directory/'out.log')+" -ErrorLog "+quote(directory/'err.log')+
                   " -Index 0 | ConvertTo-Json")
            response=subprocess.run([str(runtime),'-NoProfile','-NonInteractive','-Command',query],
                                    capture_output=True,check=True,timeout=15)
            self.assertEqual(json.loads(response.stdout)['exit_code'],7)


if __name__=='__main__':unittest.main()
