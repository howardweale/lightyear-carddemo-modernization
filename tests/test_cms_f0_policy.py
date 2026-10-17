"""Offline boundary fixtures only; CI runs these tests, not a local CMS workload."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import unittest
from unittest.mock import patch
from tools.cms import f0_probe, f0_smoke
from tools.cms.f0_policy import compile_outcome, diagnostic_metadata, publish, require_smoke, require_java


class PolicyTests(unittest.TestCase):
    def test_fixture_build_failure_has_a_failing_outcome(self):
        row=dict(package='fixture.zip',program='FIXTURE',source_sha256='a'*64,dialect='ibm',returncode=1,
            diagnostic_metadata=diagnostic_metadata('fixture:1: error: build failed'))
        outcome=compile_outcome([row],[])
        self.assertFalse(outcome['complete']);self.assertEqual(1,len(outcome['unexpected_failures']))
        with self.assertRaises(SystemExit):f0_probe.require_compile(outcome)
        with self.assertRaises(SystemExit):require_smoke({'build_returncode':1,'complete':False})

    def test_expected_limitations_bind_source_and_diagnostic_not_just_program(self):
        row=dict(package='fixture.zip',program='FIXTURE',source_sha256='a'*64,dialect='mf',returncode=1,
            diagnostic_metadata=diagnostic_metadata('fixture:1: error: missing external facility'))
        item=dict(package=row['package'],program=row['program'],source_sha256=row['source_sha256'],dialect='mf',returncode=1,
            diagnostic_sha256=row['diagnostic_metadata']['normalized_sha256'],reason='explicit fixture limitation')
        self.assertTrue(compile_outcome([row],[item])['complete'])
        self.assertFalse(compile_outcome([row],[item])['all_programs_compiled'])
        row['diagnostic_metadata']=diagnostic_metadata('runner permission denied')
        self.assertFalse(compile_outcome([row],[item])['complete'])
        self.assertFalse(compile_outcome([],[])['complete'])
        successful=dict(row,returncode=0)
        self.assertFalse(compile_outcome([successful],[],[])['complete'])

    def test_source_quoting_is_detected_and_raw_text_never_published(self):
        secret='MOVE PRIVATE-RATE TO PRIVATE-PAYMENT'
        metadata=diagnostic_metadata('42 | '+secret,[secret])
        self.assertTrue(metadata['possible_source_quote'])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'compile-logs').mkdir();(root/'compile-logs/raw.txt').write_text(secret)
            (root/'compile-results.json').write_text(json.dumps(dict(results=[dict(program='FIXTURE',dialect='ibm',diagnostics=secret,diagnostic_metadata=metadata)],outcome={'complete':False})))
            publish(root);public=(root/'public/receipt.json').read_text()
            self.assertNotIn(secret,public);self.assertNotIn('diagnostics"',public)
            self.assertEqual(['receipt.json'],[p.name for p in (root/'public').iterdir()])

    def test_failed_java_probe_cannot_be_success(self):
        for result in ({'error':'startup'}, {'paths':['/price'],'owned_process_stopped':True,'claims':[]},
                       {'paths':['/price'],'owned_process_stopped':True,'claims':[{'http_status':400}]*5}):
            self.assertFalse(require_java(result,True))
        self.assertTrue(require_java({'paths':['/price'],'owned_process_stopped':True,'claims':[{'http_status':200}]*5},True))

    def test_fixture_compiler_failure_is_nonzero_and_receipt_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);packages={}
            for name in ('files-fy-20215-software-release.zip','cy-20212-esrd-main-frame-pricing-programs.zip'):
                path=root/name
                with zipfile.ZipFile(path,'w') as archive:
                    archive.writestr('FIXTURE',"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. FIXTURE.\n       PROCEDURE DIVISION.\n           GOBACK.\n")
                packages[name]=path
            failure=subprocess.CompletedProcess(['fixture-cobc'],1,stdout='',stderr='fixture: compilation failed')
            with patch.object(f0_probe.subprocess,'check_output',return_value='cobc (GnuCOBOL) 3.1.2'),patch.object(f0_probe.subprocess,'run',return_value=failure):
                with self.assertRaisesRegex(SystemExit,'unexpected-incompleteness'):f0_probe.compile_probe(root,packages,[])
            receipt=json.loads((root/'compile-results.json').read_bytes())
            self.assertEqual(2,len(receipt['outcome']['unexpected_failures']))
            self.assertFalse(receipt['outcome']['complete'])
            self.assertTrue(all('diagnostics' not in row for row in receipt['results']))
