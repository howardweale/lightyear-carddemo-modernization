import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def run_cli(self,*args):
        return subprocess.run([sys.executable,'-m','lightyear_mainframe',*map(str,args)],
                              cwd=ROOT,capture_output=True,text=True)

    def test_inventory_and_unobserved_baseline_files(self):
        source=self.root/'source';source.mkdir()
        (source/'ONE.CBL').write_text('       PROCEDURE DIVISION.\n           IF A CONTINUE END-IF.\n')
        out=self.root/'out'
        result=self.run_cli('inventory','--source',source,'--output',out)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertEqual(2,json.loads((out/'inventory.json').read_text())['summary']['outcomes'])
        self.assertIn('Runtime coverage is **unobserved**',(out/'report.md').read_text())
        measured=self.root/'coverage.json'
        result=self.run_cli('coverage','--inventory',out/'inventory.json','--output',measured)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertIsNone(json.loads(measured.read_text())['coverage_percent'])

    def test_binary_decode_writes_exact_values_and_bytes(self):
        data=self.root/'sample.bin';data.write_bytes(bytes.fromhex((ROOT/'spec/mainframe/packed-golden.hex').read_text().strip()))
        result=self.run_cli('decode','--copybook',ROOT/'spec/mainframe/copybooks/ARRIVAL.cpy',
                            '--input',data,'--codec','cp037','--output',self.root/'out.json')
        self.assertEqual(0,result.returncode,result.stderr)
        record=json.loads((self.root/'out.json').read_text())['records'][0]
        self.assertEqual(data.read_bytes().hex(),record['raw_hex'])
        self.assertEqual('-123.45',record['fields'][2]['value'])

    def test_bad_source_or_truncated_record_fails_without_success_artifact(self):
        empty=self.root/'empty';empty.mkdir()
        result=self.run_cli('inventory','--source',empty,'--output',self.root/'out')
        self.assertEqual(2,result.returncode)
        self.assertFalse((self.root/'out/inventory.json').exists())
        data=self.root/'bad.bin';data.write_bytes(b'\xf0')
        result=self.run_cli('decode','--copybook',ROOT/'spec/mainframe/copybooks/ARRIVAL.cpy',
                            '--input',data,'--codec','cp037','--output',self.root/'bad.json')
        self.assertEqual(2,result.returncode)
        self.assertFalse((self.root/'bad.json').exists())

    def test_extended_rdw_decode_and_explicit_profiles(self):
        fixture=json.loads((ROOT/'spec/mainframe/extended-golden.json').read_text())
        data=self.root/'bank.rdw'
        data.write_bytes(bytes.fromhex(''.join(r['rdw_hex']+r['payload_hex'] for r in fixture['records'])))
        choices=self.root/'choices.json';choices.write_text(json.dumps(fixture['redefines']))
        options=('decode','--copybook',ROOT/'spec/mainframe/copybooks/BANKEXT.cpy','--input',data,
                 '--codec','cp037','--framing','rdw','--redefines',choices)
        result=self.run_cli(*options,'--output',self.root/'missing.json')
        self.assertEqual(2,result.returncode)
        self.assertFalse((self.root/'missing.json').exists())
        result=self.run_cli(*options,'--binary-byteorder','big','--binary-truncation','std','--output',self.root/'bank.json')
        self.assertEqual(0,result.returncode,result.stderr)
        records=json.loads((self.root/'bank.json').read_text())['records']
        self.assertEqual(2,len(records))
        self.assertEqual('-1.23',records[1]['fields'][-2]['value'])
