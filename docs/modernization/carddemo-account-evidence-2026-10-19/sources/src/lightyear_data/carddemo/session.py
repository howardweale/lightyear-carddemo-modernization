"""Bounded public-source sign-on session; no deployed authentication service."""
from .screens import receive
from .schema import copybook, pinned
from pathlib import Path
import re


def signon_bindings(user_copybook=None):
    root=Path(__file__).resolve().parents[3]/'spec/modernization'
    data=root/'carddemo-data';screens=root/'carddemo-screens'
    pinned(data);pinned(screens)
    text=user_copybook if user_copybook is not None else (data/'upstream/app/cpy/CSUSR01Y.cpy').read_text(encoding='utf-8')
    layout,_=copybook(text,'app/cpy/CSUSR01Y.cpy')
    fields={f.path.rsplit('.',1)[-1]:f for f in layout.fields}
    messages=(screens/'upstream/app/cpy/CSMSG01Y.cpy').read_text(encoding='utf-8')
    constants={name:value.rstrip() for name,value in re.findall(r"(CCDA-MSG-[A-Z-]+)\s+PIC X\(50\) VALUE\s+'([^']*)'",messages)}
    if set(constants)!={'CCDA-MSG-THANK-YOU','CCDA-MSG-INVALID-KEY'}:raise ValueError('message declarations changed')
    program=(screens/'upstream/app/cbl/COSGN00C.cbl').read_text(encoding='utf-8')
    literals=re.findall(r"MOVE\s+'([^']+)'\s+TO\s+WS-MESSAGE",program)
    return layout,fields,constants,set(literals)



class SignonSession:
    def __init__(self, screen, repository, *, user_copybook=None):
        self.screen,self.repository=screen,repository
        self.program='COSGN00C';self.user=None;self.user_type=None
        self.layout,self.fields,self.constants,self.messages=signon_bindings(user_copybook)

    def submit(self, aid, values=None):
        if self.program=='ENDED':raise ValueError('session-ended')
        if aid=='PF3':
            self.program='ENDED' if self.program=='COSGN00C' else 'COSGN00C'
            self.user=None;self.user_type=None
            return self.result(self.constants['CCDA-MSG-THANK-YOU'] if self.program=='ENDED' else '')
        if self.program!='COSGN00C':return self.result('blocked-unimplemented-program')
        if aid!='ENTER':return self.result(self.constants['CCDA-MSG-INVALID-KEY'])
        fields=receive(self.screen,values or {})
        user=fields.get('USERID',b'\x40'*8);password=fields.get('PASSWD',b'\x40'*8)
        # COBOL checks all spaces or all low-values before UPPER-CASE.
        if user in (b'\x40'*8,b'\0'*8):return self.result('Please enter User ID ...','USERID')
        if password in (b'\x40'*8,b'\0'*8):return self.result('Please enter Password ...','PASSWD')
        user=user.decode('cp037').upper().encode('cp037');password=password.decode('cp037').upper().encode('cp037')
        status,raw=self.repository.read(user)
        if status=='NOTFND':return self.result('User not found. Try again ...','USERID')
        if status!='NORMAL' or raw is None or len(raw)!=self.layout.record_length:return self.result('Unable to verify the User ...','USERID')
        pwd=self.fields['SEC-USR-PWD'];kind=self.fields['SEC-USR-TYPE']
        if raw[pwd.offset:pwd.offset+pwd.length]!=password:return self.result('Wrong Password. Try again ...','PASSWD')
        self.user=user;self.user_type=raw[kind.offset:kind.offset+kind.length].decode('cp037')
        self.program='COADM01C' if self.user_type=='A' else 'COMEN01C'
        return self.result('')

    def result(self,message,cursor=None):
        if message and message not in self.messages and message not in self.constants.values() and message!='blocked-unimplemented-program':raise ValueError('unbound source message')
        return dict(program=self.program,message=message,cursor=cursor,user_type=self.user_type,
            scope='source-derived sign-on model only; downstream program business behavior unimplemented')
