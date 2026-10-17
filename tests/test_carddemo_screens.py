from pathlib import Path
import unittest
from lightyear_data.carddemo.screens import parse, receive, render, split_options

ROOT=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens/upstream'


class ScreenTests(unittest.TestCase):
    def test_source_signon_coordinates_input_and_hidden_password(self):
        model=parse((ROOT/'app/bms/COSGN00.bms').read_bytes(),'app/bms/COSGN00.bms')['maps'][0]
        user=next(f for f in model['fields'] if f['name']=='USERID')
        self.assertEqual((19-1)*80+43,user['data_offset'])
        self.assertEqual(b'\xc1\xf1'+b'\x40'*6,receive(model,{'USERID':'A1'})['USERID'])
        for values in ({'USERID':'ninechars'},{'TITLE01':'modified'},{'invented':'x'}):
            with self.assertRaises(ValueError):receive(model,values)
        html=render(model)
        self.assertIn('type="password"',html)
        self.assertIn('autofocus',html)
        self.assertNotIn('fetch(',html)

    def test_quoted_commas_and_escaped_quotes(self):
        self.assertEqual("'A,B''C'",split_options("INITIAL='A,B''C',POS=(1,2)")['INITIAL'])
        with self.assertRaises(ValueError):split_options('LENGTH=8,LENGTH=9')

    def test_unsupported_or_overflow_fails_closed(self):
        raw=b"MAP DFHMSD TYPE=MAP\nSCR DFHMDI SIZE=(24,80)\nF DFHMDF LENGTH=8,POS=(24,79)\n"
        with self.assertRaisesRegex(ValueError,'outside-map'):parse(raw,'fixture')
        with self.assertRaisesRegex(ValueError,'unsupported'):parse(raw.replace(b'LENGTH=8',b'UNKNOWN=YES,LENGTH=8'),'fixture')
