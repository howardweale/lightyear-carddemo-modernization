"""Actual GnuCOBOL indexed I/O probes at each POSTTRAN output layout's widths."""
from pathlib import Path
from lightyear_mainframe.legacy_twin import FILES,FLAGS,execute,receipt,sha

def probe(output):
    output.mkdir()
    results={}
    for dd in ('ACCTFILE','TCATBALF','TRANFILE'):
        length,key=FILES['POSTTRAN'][dd]
        folder=output/dd;folder.mkdir()
        source=folder/'probe.cob'
        source.write_text(f'''identification division.
program-id. postingio.
environment division.
input-output section.
file-control.
select f assign to 'probe.idx' organization indexed access dynamic
 record key k file status fs.
data division.
file section.
fd f.
01 r.
 05 k pic x({key}).
 05 v pic x({length-key}).
working-storage section.
01 fs pic xx.
procedure division.
 open output f
 move all '1' to k move all 'a' to v write r
 display 'WRITE=' fs
 write r display 'DUPLICATE=' fs
 close f
 open i-o f
 move all '1' to k read f key k display 'READ=' fs
 move all 'b' to v rewrite r display 'REWRITE=' fs
 move all '1' to k read f key k
 if v not = all 'b' stop run returning 65 end-if
 move all '9' to k read f key k display 'NOT-FOUND=' fs
 move all '2' to k move all 'c' to v write r display 'WRITE-NEW=' fs
 close f
 stop run returning 0.
''',encoding='ascii')
        execute(['cobc','-x','-free',*FLAGS,source,'-o',folder/'probe'],folder,folder/'compile')
        run=execute([folder/'probe'],folder,folder/'run')
        observed=dict(line.split('=',1) for line in run.stdout.decode().splitlines())
        results[dd]={'record_length':length,'key_length':key,'observed':observed,'source_sha256':sha(source.read_bytes()),'zos_confirmation':False}
        if observed!={'WRITE':'00','DUPLICATE':'22','READ':'00','REWRITE':'00','NOT-FOUND':'23','WRITE-NEW':'00'}:
            receipt(output/'posting-io.json',phase='posting-io',results=results,status='unexpected-file-status')
            raise AssertionError('POSTTRAN indexed I/O probe changed: '+dd)
    return receipt(output/'posting-io.json',phase='posting-io',results=results,status='engineering-probes-completed')
