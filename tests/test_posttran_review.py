import json,tempfile,unittest
from pathlib import Path
from lightyear_mainframe.posttran_review import SHEET,packet,body,render,sign,verify
from lightyear_mainframe.zos_evidence import initialize_key,Signer
class ReviewTests(unittest.TestCase):
    def test_complete_readable_public_page(self):
        s=json.loads(SHEET.read_bytes());page=render(s)
        self.assertEqual(10,page.count('<section>'));self.assertEqual(10,len(packet(s)['decisions']))
        self.assertIn('379:',page);self.assertIn('Unsigned decisions',page)
        with self.assertRaises(ValueError):body(s,packet(s),'Howard')
    def test_explicit_operator_signing_and_tamper(self):
        s=json.loads(SHEET.read_bytes());p=packet(s);p['reviewer']='Test operator'
        for r in p['decisions']:r.update(decision='investigate',reason='Test-only source review')
        with tempfile.TemporaryDirectory() as d:
            k=Path(d)/'test.pem';initialize_key(k);signer=Signer(k)
            result=sign(s,p,'Test operator',signer)
            self.assertFalse(verify(s,result,signer.public)['all_accepted'])
            result['decisions'][0]['decision']='accept'
            with self.assertRaises(ValueError):verify(s,result,signer.public)
