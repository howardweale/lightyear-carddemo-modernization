"""CI prepares a public loader-only capture package; never submits a z/OS job."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from lightyear_mainframe.scenario_generation import case
from lightyear_mainframe.records import load_copybook, decode_fixed

ROOT=Path(__file__).resolve().parents[1]


def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    binding=json.loads((ROOT/'docs/factory/capture-kit-intcalc-duplicate-category-2026-10-16.json').read_bytes())
    for source in binding['bound_sources']:
        if sha256((ROOT/source['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=source['lf_sha256']:raise ValueError('capture-source-changed')
    job,_,images,_=case(binding['scenario_id'])
    lines=images['TCATBALF'].splitlines()
    if job!='INTCALC' or len(lines)!=2 or lines[0]!=lines[1] or len(lines[0])!=50:raise ValueError('capture-duplicate-fixture')
    raw=b''.join(lines).decode('ascii').encode('cp037')
    decode_fixed(load_copybook(ROOT/'spec/mainframe/copybooks/CVTRA01Y.cpy'),raw)
    files={'TCATBALF-control.ebcdic':raw[:50],'TCATBALF-duplicate.ebcdic':raw}
    for name,value in files.items():(output/name).write_bytes(value)
    # No DELETE or application step: operator must allocate fresh named datasets.
    sysin=""" DEFINE CLUSTER (NAME(OPERATOR.FRESH.KSDS) INDEXED -
   KEYS(17 0) RECORDSIZE(50 50) TRACKS(1 1))
 IF LASTCC = 0 THEN DO
   REPRO INFILE(INPUT) OUTDATASET(OPERATOR.FRESH.KSDS)
 END
 LISTCAT ENTRIES(OPERATOR.FRESH.KSDS) ALL
"""
    (output/'loader.sysin.template').write_text(sysin,encoding='ascii')
    manifest={**binding,'schema':'zos-loader-capture-package/1','lrecl':50,'key_offset':0,'key_length':17,
        'codec':'cp037','transfer':'binary, FB records without newline/RDW/BDW',
        'files':{k:dict(sha256=sha256(v).hexdigest(),bytes=len(v),records=len(v)//50) for k,v in files.items()},
        'control_expected':'one record admitted; capture actual return code and output count',
        'duplicate_expected':'duplicate primary-key refusal during REPRO; capture actual code/messages; not precredited',
        'observed_zos_result':None,'effective':False,'release_authorized':False}
    manifest['content_sha256']=sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (output/'README.md').write_text('''# Maintec loader-domain confirmation package

Unsigned preparation only. Operator approval and site JCL/security review precede any submission.
Use two separate fresh disposable KSDS names, one per input; never reuse a populated cluster.
Transfer each public input binary as FB LRECL 50. Substitute the approved fresh dataset name
in loader.sysin.template and bind INPUT to the corresponding sequential file. Run IDCAMS
only: this package must not execute CBACT04C or any business application.

Capture submitted JCL/SYSIN, complete JES and IDCAMS SYSPRINT, step return code, LISTCAT
definition, binary input SHA-256 and record count, and admitted-record/control totals.
The control must admit one record. The duplicate case must show an actual duplicate-key
refusal. Neither an infrastructure failure nor a missing job log confirms the proposal.
Keep actual LPAR results in the private arrival path; public publication requires approval.
No result is supplied by this package and no z/OS-facing exclusion is applied.
''',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');build(parser.parse_args().output)
