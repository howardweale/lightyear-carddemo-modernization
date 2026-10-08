"""Verify the host-owned, live revocation channel on every guidance read.

The channel and its head must be writable only by the authority, never the agent.
A durable watermark outside the projection detects rollback across reader restarts;
signed 15-minute validity bounds first-read staleness. An administrator who can
roll back the watermark and clock remains outside this trust boundary. Protect
that state with host ACLs. A changed head without a matching list fails closed.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from lightyear_control_tower.decisions import verify_envelope, digest


class RevocationReader:
    def __init__(self, directory, binding, projection_sha256, *, state_directory=None, now=None):
        self.directory=Path(directory);self.binding=binding;self.projection=projection_sha256
        self.sequence=0;self.last=None
        self.clock=now or (lambda:datetime.now(timezone.utc))
        self.state_directory=Path(state_directory) if state_directory else Path.home()/'.lightyear/graph-revocation-state'
        self.state_directory.mkdir(parents=True,exist_ok=True)
        self.state_path=self.state_directory/'highest-sequences.sqlite3'

    def watermark(self,row):
        # The host owns this directory; it is outside the projection/channel.
        if self.state_path.is_symlink():raise ValueError('revocation-state-link')
        key=self.binding['channel']+':'+self.projection
        identity=digest(dict(ledger_head=row['ledger_head'],revoked=row['revoked']))
        with closing(sqlite3.connect(self.state_path,timeout=15)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS watermarks (channel TEXT PRIMARY KEY, sequence INTEGER NOT NULL, identity TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT sequence,identity FROM watermarks WHERE channel=?',(key,)).fetchone()
            if prior and (row['sequence']<prior[0] or row['sequence']==prior[0] and identity!=prior[1]):
                raise ValueError('revocation-head-rollback')
            db.execute('INSERT OR REPLACE INTO watermarks VALUES (?,?,?)',(key,row['sequence'],identity))

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
        for record in (head,row):
            try:
                issued=datetime.fromisoformat(record['issued_at']);until=datetime.fromisoformat(record['valid_until'])
                current=self.clock()
                if issued.tzinfo is None or until.tzinfo is None or not issued<=current<until or not 0<(until-issued).total_seconds()<=900:
                    raise ValueError('revocation-head-expired')
            except (KeyError,TypeError):raise ValueError('revocation-validity-required')
        if (head['issued_at'],head['valid_until']) != (row['issued_at'],row['valid_until']):raise ValueError('revocation-head-validity')
        if (head['schema']!='annotation-live-head/1' or row['schema']!='annotation-revocations/1' or
                head['ledger_head']!=row['ledger_head'] or head['sequence']!=row['sequence'] or
                row['projection_sha256']!=self.projection or
                type(row['sequence']) is not int or row['sequence']<self.sequence or
                row['sequence']==self.sequence and self.last is not None and digest(dict(ledger_head=row['ledger_head'],revoked=row['revoked']))!=self.last):
            raise ValueError('revocation-head-or-projection')
        if not isinstance(row['revoked'],list) or not all(isinstance(v,str) for v in row['revoked']):
            raise ValueError('revocation-list')
        self.watermark(row)
        self.sequence=row['sequence'];self.last=digest(dict(ledger_head=row['ledger_head'],revoked=row['revoked']))
        return set(row['revoked'])
