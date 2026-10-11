"""Real indexed storage experiment: cp037 primary-key bytes, no twin promotion."""
from pathlib import Path
from lightyear_mainframe.legacy_twin import execute,FLAGS,receipt,sha,linux_platform

KEYS=['A','Z','a','z','0','9',' ']
PROGRAM='''identification division.
program-id. indexorder.
environment division.
input-output section.
file-control.
select raw-file assign to 'keys.bin' organization sequential.
select indexed-file assign to 'keys.idx' organization indexed access dynamic
 record key k file status fs.
data division.
file section.
fd raw-file.
01 raw-key pic x.
fd indexed-file.
01 r.
 05 k pic x.
 05 v pic x.
working-storage section.
01 fs pic xx.
01 n pic 999.
procedure division.
 open input raw-file open output indexed-file
 perform 7 times
  read raw-file
  move raw-key to k move 'x' to v write r
  if fs not = '00' stop run returning 65 end-if
 end-perform
 write r display 'DUPLICATE=' fs
 close indexed-file raw-file
 open i-o indexed-file
 perform 7 times
  read indexed-file next record
  if fs not = '00' stop run returning 65 end-if
  compute n = function ord(k) - 1
  display 'KEY=' n
 end-perform
 read indexed-file next record display 'EOF=' fs
 close indexed-file
 open input raw-file open i-o indexed-file
 read raw-file move raw-key to k read indexed-file key k
 display 'RANDOM=' fs
 move 'y' to v rewrite r display 'REWRITE=' fs
 read indexed-file key k
 if v not = 'y' stop run returning 66 end-if
 start indexed-file key >= k display 'START=' fs
 read indexed-file next record
 if k not = raw-key stop run returning 67 end-if
 close indexed-file raw-file
 stop run returning 0.
'''

def probe(output):
    linux_platform();output=Path(output).resolve();output.mkdir()
    results={}
    for codec in ('ascii','cp037'):
        folder=output/codec;folder.mkdir();source=folder/'probe.cob';source.write_text(PROGRAM,encoding='ascii')
        (folder/'keys.bin').write_bytes(''.join(KEYS).encode(codec))
        execute(['cobc','-x','-free',*FLAGS,source,'-o',folder/'probe'],folder,folder/'compile')
        run=execute([folder/'probe'],folder,folder/'run');lines=run.stdout.decode().splitlines()
        order=[bytes([int(line.split('=')[1])]).decode(codec) for line in lines if line.startswith('KEY=')]
        statuses=dict(line.split('=') for line in lines if not line.startswith('KEY='))
        expected=sorted(KEYS,key=lambda k:k.encode(codec))
        results[codec]=dict(order=order,expected=expected,statuses=statuses,source_sha256=sha(source.read_bytes()))
        if order!=expected or statuses!={'DUPLICATE':'22','EOF':'10','RANDOM':'00','REWRITE':'00','START':'00'}:
            receipt(output/'index-order.json',phase='indexed-order-probe',results=results,status='failed')
            raise AssertionError('indexed cp037 experiment mismatch')
    return receipt(output/'index-order.json',phase='indexed-order-probe',results=results,
                   scope='Primary one-byte keys only; no full program adapter or z/OS equivalence',decimal_key_restriction_retained=True)

if __name__=='__main__':
    import sys
    probe(Path(sys.argv[1]))
