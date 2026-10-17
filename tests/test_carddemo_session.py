from hashlib import sha256
import json
from pathlib import Path
import unittest
from lightyear_data.carddemo.screens import parse
from lightyear_data.carddemo.session import SignonSession

ROOT=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens'


class SessionTests(unittest.TestCase):
    def setUp(self):
        provenance=json.loads((ROOT/'provenance.json').read_bytes())
        path='app/cbl/COSGN00C.cbl';raw=(ROOT/'upstream'/path).read_bytes()
        self.assertEqual(provenance['files'][path]['sha256'],sha256(raw).hexdigest())
        self.screen=parse((ROOT/'upstream/app/bms/COSGN00.bms').read_bytes(),'COSGN00.bms')['maps'][0]
        class Users:
            def read(self,key):
                if key==b'FAIL    '.decode('ascii').encode('cp037'):return '90',None
                users={'USER0001':'U','ADMIN001':'A'}
                name=key.decode('cp037')
                if name not in users:return 'NOTFND',None
                return 'NORMAL',(name+' '*40+'PASSWORD'+users[name]+' '*23).encode('cp037')
        self.session=SignonSession(self.screen,Users())

    def test_source_argument_cases_and_session_exit(self):
        cases=[('ENTER',{},'Please enter User ID ...','USERID'),
            ('ENTER',{'USERID':'USER0001'},'Please enter Password ...','PASSWD'),
            ('ENTER',{'USERID':'missing','PASSWD':'PASSWORD'},'User not found. Try again ...','USERID'),
            ('ENTER',{'USERID':'FAIL','PASSWD':'PASSWORD'},'Unable to verify the User ...','USERID'),
            ('ENTER',{'USERID':'USER0001','PASSWD':'bad'},'Wrong Password. Try again ...','PASSWD'),
            ('PF1',{},'Invalid key pressed. Please see below...',None)]
        for aid,values,message,cursor in cases:
            result=self.session.submit(aid,values)
            self.assertEqual((message,cursor,'COSGN00C'),(result['message'],result['cursor'],result['program']))
        result=self.session.submit('ENTER',{'USERID':'user0001','PASSWD':'password'})
        self.assertEqual(('COMEN01C','U'),(result['program'],result['user_type']))
        self.assertEqual('blocked-unimplemented-program',self.session.submit('ENTER',{})['message'])
        self.assertEqual('COSGN00C',self.session.submit('PF3')['program'])
        self.assertIsNone(self.session.user)
        self.assertEqual('ENDED',self.session.submit('PF3')['program'])
        with self.assertRaises(ValueError):self.session.submit('ENTER')

    def test_copybook_change_moves_password_offset(self):
        from lightyear_data.carddemo.session import signon_bindings
        raw=(ROOT.parent/'carddemo-data/upstream/app/cpy/CSUSR01Y.cpy').read_text(encoding='utf-8')
        original=signon_bindings(raw);changed=signon_bindings(raw.replace('PIC X(20)','PIC X(21)'))
        self.assertEqual(original[1]['SEC-USR-PWD'].offset+2,changed[1]['SEC-USR-PWD'].offset)
        self.assertEqual(original[0].record_length+2,changed[0].record_length)

    def test_admin_route_and_protected_field_injection(self):
        with self.assertRaises(ValueError):self.session.submit('ENTER',{'TITLE01':'forged'})
        result=self.session.submit('ENTER',{'USERID':'ADMIN001','PASSWD':'PASSWORD'})
        self.assertEqual('COADM01C',result['program'])
