"""Bounded public-source sign-on session; no deployed authentication service."""
from .screens import receive


class SignonSession:
    def __init__(self, screen, repository):
        self.screen,self.repository=screen,repository
        self.program='COSGN00C';self.user=None;self.user_type=None

    def submit(self, aid, values=None):
        if self.program=='ENDED':raise ValueError('session-ended')
        if aid=='PF3':
            self.program='ENDED' if self.program=='COSGN00C' else 'COSGN00C'
            self.user=None;self.user_type=None
            return self.result('exit' if self.program=='ENDED' else 'signon')
        if self.program!='COSGN00C':return self.result('blocked-unimplemented-program')
        if aid!='ENTER':return self.result('invalid-aid')
        fields=receive(self.screen,values or {})
        user=fields.get('USERID',b'\x40'*8);password=fields.get('PASSWD',b'\x40'*8)
        # COBOL checks all spaces or all low-values before UPPER-CASE.
        if user in (b'\x40'*8,b'\0'*8):return self.result('Please enter User ID ...','USERID')
        if password in (b'\x40'*8,b'\0'*8):return self.result('Please enter Password ...','PASSWD')
        user=user.decode('cp037').upper().encode('cp037');password=password.decode('cp037').upper().encode('cp037')
        status,raw=self.repository.read(user)
        if status=='23':return self.result('User not found. Try again ...','USERID')
        if status!='00' or raw is None or len(raw)!=80:return self.result('Unable to verify the User ...','USERID')
        if raw[48:56]!=password:return self.result('Wrong Password. Try again ...','PASSWD')
        self.user=user;self.user_type=raw[56:57].decode('cp037')
        self.program='COADM01C' if self.user_type=='A' else 'COMEN01C'
        return self.result('transfer')

    def result(self,message,cursor=None):
        return dict(program=self.program,message=message,cursor=cursor,user_type=self.user_type,
            scope='source-derived sign-on model only; downstream program business behavior unimplemented')
