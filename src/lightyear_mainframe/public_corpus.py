"""Reproducible decoding check against the pinned public CardDemo fixtures."""
from pathlib import Path
import subprocess

from .records import decode_fixed, load_copybook
from .source import sha

CARDDEMO_COMMIT = '59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e'
DATASETS = [('CVACT01Y', 'ACCTDATA', 50), ('CVTRA05Y', 'DALYTRAN', 300),
            ('CVTRA01Y', 'TCATBALF', 50), ('CVTRA02Y', 'DISCGRP', 51), ('CVACT03Y', 'CARDXREF', 50)]


def verify_public(root: Path):
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != CARDDEMO_COMMIT:
        raise ValueError('public fixture verification requires the pinned CardDemo commit')
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True).strip():
        raise ValueError('public fixture verification requires a clean checkout')
    datasets = []
    for copybook, dataset, expected_count in DATASETS:
        path = root/'app/data/EBCDIC'/f'AWS.M2.CARDDEMO.{dataset}.PS'
        copy = root/'app/cpy'/f'{copybook}.cpy'
        layout = load_copybook(copy)
        raw = path.read_bytes()
        decoded = decode_fixed(layout, raw, codec='cp037', sign_policy='preferred')
        if len(decoded) != expected_count:
            raise ValueError('unexpected public fixture record count')
        restored = b''.join(bytes.fromhex(f['raw_hex']) for record in decoded for f in record['fields'])
        if restored != raw: raise ValueError('decoder did not retain every original byte')
        datasets.append(dict(path=path.relative_to(root).as_posix(), sha256=sha(raw),
                             copybook=copy.relative_to(root).as_posix(), copybook_sha256=layout.copybook_sha256,
                             record_length=layout.record_length, records=len(decoded), original_bytes_preserved=True))
    return dict(schema_version='1.0', source_commit=commit, evidence_class='local_observed',
                observation='Local decoding of public repository fixtures; no program was executed on z/OS.',
                codec='cp037', sign_policy='preferred', datasets=datasets,
                records=sum(d['records'] for d in datasets), mainframe_equivalent=False)
