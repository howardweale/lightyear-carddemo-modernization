"""Verify the host-owned, live revocation channel on every guidance read.

The channel and its head must be writable only by the authority, never the agent.
Signatures do not prevent an administrator rolling back both files; deployment
must protect this host state. A changed head without a matching list fails closed.
"""
import json
from pathlib import Path
from lightyear_control_tower.decisions import verify_envelope, digest


class RevocationReader:
    def __init__(self, directory, binding, projection_sha256):
        self.directory=Path(directory);self.binding=binding;self.projection=projection_sha256
        self.sequence=0;self.last=None

    def read(self):
        key=self.binding['public_key_pem'].encode()
        def verified(name):
            p=self.directory/name
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('revocation-link')
            v=json.loads(p.read_bytes())
            if not verify_envelope(v,key):raise ValueError('revocation-signature')
            if v['channel']!=self.binding['channel']:raise ValueError('revocation-channel')
            return v
        head=verified('head.json');row=verified('revocations.json')
        if (head['schema']!='annotation-live-head/1' or row['schema']!='annotation-revocations/1' or
                head['ledger_head']!=row['ledger_head'] or head['sequence']!=row['sequence'] or
                row['projection_sha256']!=self.projection or
                type(row['sequence']) is not int or row['sequence']<self.sequence or
                row['sequence']==self.sequence and self.last is not None and row['content_sha256']!=self.last):
            raise ValueError('revocation-head-or-projection')
        if not isinstance(row['revoked'],list) or not all(isinstance(v,str) for v in row['revoked']):
            raise ValueError('revocation-list')
        self.sequence=row['sequence'];self.last=row['content_sha256']
        return set(row['revoked'])
