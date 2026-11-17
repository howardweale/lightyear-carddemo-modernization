"""Deterministic private INTCALC input generation; never runs an oracle or freeze.

Only Howard launches the CLI. CI may use declared synthetic seeds; agents must
not run this generator. Expected answers require a separate qualified encrypted
reference stage. No retired cases, expected outputs or prior runs are imported.
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
import warnings

from lightyear_mainframe.records import load_copybook
from tools.intcalc_reference_execution import preferred_signs, bridge, DDS, Refused as ReferenceRefused

COPYBOOKS = {'ACCTFILE':'CVACT01Y.cpy','TCATBALF':'CVTRA01Y.cpy',
             'DISCGRP':'CVTRA02Y.cpy','XREFFILE':'CVACT03Y.cpy'}
LIMIT = 'open-source reference, not mainframe-proven; inputs only, unqualified'


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok: raise Refused(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Draws:
    """Labelled HMAC counter stream with rejection sampling, no global RNG."""
    def __init__(self, seed):
        require(type(seed) is bytes and len(seed)==32,'seed-shape')
        self.key=seed

    def below(self, label, size):
        require(type(label) is str and type(size) is int and 1<=size<=2**64,'draw-domain')
        ceiling=2**256-(2**256 % size)
        for counter in range(1024):
            value=int.from_bytes(hmac.digest(self.key,
                b'intcalc-fresh-inputs/1\0'+label.encode('ascii')+b'\0'+str(counter).encode(),'sha256'),'big')
            if value<ceiling:return value % size
        raise Refused('draw-exhausted')


def encode(field,value):
    require(field.usage=='DISPLAY' and not field.separate,'input-layout')
    if field.digits:
        require(type(value) is int and (field.signed or value>=0),'field-value')
        digits=str(abs(value)).rjust(field.digits,'0')
        require(len(digits)==field.digits==field.length,'field-overflow')
        data=bytearray(digits.encode('cp037'))
        if field.signed:
            require(field.sign in ('LEADING','TRAILING'),'input-layout')
            position=0 if field.sign=='LEADING' else len(data)-1
            data[position]=(0xD0 if value<0 else 0xC0)|(data[position]&15)
        return bytes(data)
    require(type(value) is str,'field-value')
    try:data=value.encode('cp037')
    except UnicodeError as exc:raise Refused('field-value') from exc
    require(len(data)<=field.length,'field-overflow')
    return data.ljust(field.length,b'\x40')


def record(layout,values):
    require(not layout.variable and not layout.overlays,'input-layout')
    data=bytearray(b'\x40'*layout.record_length);seen=set()
    for field in layout.fields:
        name=field.path.split('.')[-1]
        value=values.get(name,0 if field.digits else 'Z' if field.filler else '')
        data[field.offset:field.offset+field.length]=encode(field,value)
        if name in values:
            require(name not in seen,'ambiguous-field');seen.add(name)
    require(seen==set(values),'unknown-field')
    preferred_signs(bytes(data),layout,layout.record_length)
    return bytes(data)



REFUSAL_CODES=frozenset(('seed-shape','draw-domain','draw-exhausted','input-layout',
    'field-value','field-overflow','ambiguous-field','unknown-field','case-count',
    'input-dds','platform','private-path','private-parent','run-name','private-readback',
    'manifest-shape','generator-hash','validator-hash','records-hash','copybook-hash',
    'source-hash','arguments','attended-terminal','manifest-hash','reference-sign-layout',
    'reference-signed-zoned-nonpreferred','reference-zoned-digit','reference-zoned-digit-zone',
    'partial-record','representation-domain','encoding-roundtrip','duplicate-primary-key',
    'cp037-key-order','fresh-inputs-refused'))


def refusal_code(error):
    if isinstance(error,(Refused,ReferenceRefused)) and len(error.args)==1:
        code=error.args[0]
        if type(code) is str and code in REFUSAL_CODES:return code
    return 'fresh-inputs-refused'


def scenario(draw):
    require(type(draw) is int and 0<=draw<100,'draw-domain')
    return 0 if draw<70 else 1 if draw<85 else 2 if draw<90 else 3 if draw<95 else 4


def balance(draws,label,extreme):
    if extreme:
        value=90000000000+draws.below(label+':magnitude',10000000000)
        return -value if draws.below(label+':negative',2) else value
    return draws.below(label,2000000001)-1000000000


def rate(draws,label,extreme):
    if draws.below(label+':zero',8)==0:return 0
    return 900000+draws.below(label+':value',100000) if extreme else 1+draws.below(label+':value',3600)


def generate_inputs(seed,count,layouts):
    require(type(count) is int and 1<=count<=64,'case-count')
    require(set(layouts)==set(COPYBOOKS),'input-dds')
    draws=Draws(seed);cases=[]
    # Source-derived choices: balance sign, disclosure rate, account transitions,
    # direct/default/missing group and account/xref lookup failure branches.
    # These are public-source branches, not selected from retired-case content.
    for n in range(count):
        prefix=str(n)+':'
        mode=scenario(draws.below(prefix+'lookup-mode',100))
        extreme=draws.below(prefix+'extreme-values',16)==0
        account_count=1+draws.below(prefix+'account-count',8)
        if mode==1:account_count=max(2,account_count)  # Direct AND DEFAULT in this case.
        images={dd:[] for dd in COPYBOOKS}
        rates={}
        for a in range(account_count):
            aid=10000000000+draws.below(prefix+'account-base',1000000)*10+a
            group='G'+str(a).rjust(2,'0')
            categories=1+draws.below(prefix+str(a)+':categories',4)
            amount=lambda label,limit:draws.below(prefix+str(a)+':'+label,2*limit+1)-limit
            if not (mode==3 and a==account_count-1):
                images['ACCTFILE'].append(record(layouts['ACCTFILE'],{
                    'ACCT-ID':aid,'ACCT-GROUP-ID':group,'ACCT-ACTIVE-STATUS':'Y',
                    'ACCT-CURR-BAL':balance(draws,prefix+str(a)+':current',extreme),
                    'ACCT-CURR-CYC-CREDIT':amount('credit',99999999),
                    'ACCT-CURR-CYC-DEBIT':amount('debit',99999999)}))
            if not (mode==4 and a==account_count-1):
                images['XREFFILE'].append(record(layouts['XREFFILE'],{
                    'XREF-CARD-NUM':str(4000000000000000+aid),
                    'XREF-CUST-ID':a+1,'XREF-ACCT-ID':aid}))
            for category in range(1,categories+1):
                images['TCATBALF'].append(record(layouts['TCATBALF'],{
                    'TRANCAT-ACCT-ID':aid,'TRANCAT-TYPE-CD':'01','TRANCAT-CD':category,
                    'TRAN-CAT-BAL':balance(draws,prefix+str(a)+':balance'+str(category),extreme)}))
                # Fixed scaled integers, never binary floating-point.
                key=('DEFAULT' if mode==1 and a==account_count-1 else group,category)
                if not (mode==2 and a==account_count-1) and key not in rates:
                    rates[key]=rate(draws,prefix+str(a)+':rate'+str(category),extreme)
        for (group,category),value in sorted(rates.items()):
            images['DISCGRP'].append(record(layouts['DISCGRP'],{
                'DIS-ACCT-GROUP-ID':group,'DIS-TRAN-TYPE-CD':'01',
                'DIS-TRAN-CAT-CD':category,'DIS-INT-RATE':value}))
        # Empty balance input is a public-source EOF branch, sampled independently.
        if mode==0 and draws.below(prefix+'empty-balances',8)==0:images['TCATBALF']=[]
        joined={}
        for dd,records in images.items():
            width,key=DDS[dd]
            raw=b''.join(sorted(records,key=lambda r:r[:key]))
            preferred_signs(raw,layouts[dd],width)
            bridge(raw,width,key,layout=layouts[dd],order_observable=dd in ('ACCTFILE','TCATBALF'))
            joined[dd]=raw
        # Public domain convention: deterministic injected clock, zero sub-hundredths.
        hundredths=draws.below(prefix+'hundredths',100)
        cases.append(dict(id='HC-'+str(n+1).rjust(3,'0'),processing_date='2026111600',
            timestamp='2026-11-16-12.00.00.'+str(hundredths).rjust(2,'0')+'0000',inputs=joined))
    return cases


def private_payload(cases,source_manifest):
    return canonical(dict(schema='fresh-heldout-inputs/1',qualified=False,
        expected_outputs_present=False,named_limit=LIMIT,source_manifest=source_manifest,
        cases=[dict(c,inputs={dd:raw.hex() for dd,raw in c['inputs'].items()}) for c in cases]))


def checked_parent(path):
    require(os.name=='posix','platform')
    require(path.is_absolute() and path==path.resolve(),'private-path')
    for part in (path,*path.parents):
        info=part.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),'private-path')
    info=path.stat()
    require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'private-parent')


def persist(parent,name,payload):
    """Private input file only; a digest is the sole returned public value."""
    checked_parent(parent)
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name) is not None,'run-name')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    pfd=os.open(parent,flags)
    try:
        info=os.fstat(pfd)
        require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'private-parent')
        os.mkdir(name,0o700,dir_fd=pfd)
        dfd=os.open(name,flags,dir_fd=pfd)
        try:
            fd=os.open('inputs.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dfd)
            with os.fdopen(fd,'wb') as out:
                out.write(payload);out.flush();os.fsync(out.fileno())
            fd=os.open('inputs.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
            with os.fdopen(fd,'rb') as stream:readback=stream.read(len(payload)+1)
            require(readback==payload,'private-readback')
            os.fsync(dfd)
        finally:os.close(dfd)
        os.fsync(pfd)
    finally:os.close(pfd)
    return sha(payload)


def load_sources(root,expected):
    # Exact source-manifest bytes are independently approved before any launch.
    require(set(expected)=={'source','copybooks','generator_sha256','validator_sha256','records_sha256'},'manifest-shape')
    require(sha(Path(__file__).read_bytes())==expected['generator_sha256'],'generator-hash')
    require(sha((root/'tools/intcalc_reference_execution.py').read_bytes())==expected['validator_sha256'],'validator-hash')
    require(sha((root/'src/lightyear_mainframe/records.py').read_bytes())==expected['records_sha256'],'records-hash')
    require(set(expected['copybooks'])==set(COPYBOOKS),'input-dds')
    layouts={}
    for dd,name in COPYBOOKS.items():
        path=root/'spec/mainframe/copybooks'/name
        require(not path.is_symlink() and sha(path.read_bytes())==expected['copybooks'][dd],'copybook-hash')
        layouts[dd]=load_copybook(path)
    require(sha((root/'spec/mainframe/public-source/CBACT04C.cbl').read_bytes())==expected['source'],'source-hash')
    return layouts


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')  # Do not echo an accidental private argument.


def main(argv=None):
    parser=Parser(description='Howard-only private fresh input generation; no answers or freeze.')
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--private-parent',type=Path,required=True)
    parser.add_argument('--run-name',required=True)
    parser.add_argument('--cases',type=int,required=True)
    try:
        args=parser.parse_args(argv)
        require(os.name=='posix','platform')
        require(sys.stdin.isatty() and sys.stdout.isatty(),'attended-terminal')
        checked_parent(args.private_parent)
        raw=args.source_manifest.read_bytes()
        require(sha(raw)==args.manifest_sha256,'manifest-hash')
        expected=json.loads(raw.decode('utf-8'))
        layouts=load_sources(args.source_root,expected)
        # TTY precondition prevents getpass fallback to echoed stdin.
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            seed_text=getpass.getpass('Private seed (64 hex characters): ')
        require(re.fullmatch(r'[0-9a-fA-F]{64}',seed_text) is not None,'seed-shape')
        seed=bytes.fromhex(seed_text)
        cases=generate_inputs(seed,args.cases,layouts)
        payload=private_payload(cases,expected)
        commitment=persist(args.private_parent,args.run_name,payload)
        del seed_text,seed,cases,payload
        print(commitment)
        return 0
    except BaseException as exc:
        # Never expose dynamic exceptions, paths, values, seed or generated bytes.
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
        print(refusal_code(exc),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
