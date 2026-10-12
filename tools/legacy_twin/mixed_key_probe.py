"""Discriminating mixed-key indexed probe using the production LYKEY projection."""
from pathlib import Path
from lightyear_mainframe.cp037_twin import helper
from lightyear_mainframe.legacy_twin import FLAGS, execute, linux_platform, receipt, sha

KEYS = ['A001', '9000', 'a010', 'Z009', 'z000', '000A', 'A00z', 'A000', '0009', ' A00']
EXPECTED_CP037 = [' A00', 'a010', 'z000', 'A00z', 'A000', 'A001', 'Z009', '000A', '0009', '9000']


def program(mode):
    if mode not in ('ascii', 'cp037'):
        raise ValueError('unsupported-key-mode')
    project = "call 'LYKEY' using input-key output-key key-length" if mode == 'cp037' else 'move input-key to output-key'
    return f'''identification division.
program-id. mixedkeys.
environment division.
input-output section.
file-control.
select raw-file assign to 'keys.bin' organization sequential.
select indexed-file assign to 'keys.idx' organization indexed access dynamic
 record key physical-key file status fs.
data division.
file section.
fd raw-file recording mode F.
01 raw-key pic x(4).
fd indexed-file.
01 r.
 05 physical-key pic x(4).
 05 logical-key pic x(4).
 05 payload pic x.
working-storage section.
01 fs pic xx.
01 input-key pic x(32).
01 output-key pic x(32).
01 key-length binary-long value 4.
procedure division.
 open input raw-file open output indexed-file
 perform {len(KEYS)} times
  read raw-file
  move raw-key to input-key
  {project}
  move output-key(1:4) to physical-key
  move raw-key to logical-key move 'x' to payload write r
  if fs not = '00' stop run returning 65 end-if
 end-perform
 write r display 'DUPLICATE=' fs
 close indexed-file raw-file
 open i-o indexed-file
 perform {len(KEYS)} times
  read indexed-file next record
  if fs not = '00' stop run returning 65 end-if
  display 'KEY=' logical-key
 end-perform
 read indexed-file next record display 'EOF=' fs
 close indexed-file
 open input raw-file open i-o indexed-file
 read raw-file move raw-key to input-key
 {project}
 move output-key(1:4) to physical-key
 read indexed-file key physical-key display 'RANDOM=' fs
 if logical-key not = raw-key stop run returning 66 end-if
 move 'y' to payload rewrite r display 'REWRITE=' fs
 read indexed-file key physical-key
 if payload not = 'y' stop run returning 66 end-if
 start indexed-file key >= physical-key display 'START=' fs
 read indexed-file next record
 if logical-key not = raw-key stop run returning 67 end-if
 close indexed-file raw-file
 stop run returning 0.
'''


def probe(output):
    linux_platform()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for mode in ('ascii', 'cp037'):
        folder = output / mode
        folder.mkdir()
        source = folder / 'probe.cob'
        source.write_text(program(mode), encoding='ascii')
        key_source = folder / 'key.cob'
        key_source.write_text(helper(), encoding='ascii')
        (folder / 'keys.bin').write_bytes(''.join(KEYS).encode('ascii'))
        execute(['cobc', '-x', '-free', *FLAGS, source, key_source, '-o', folder / 'probe'], folder, folder / 'compile')
        run = execute([folder / 'probe'], folder, folder / 'run')
        lines = run.stdout.decode('ascii').splitlines()
        order = [line[4:] for line in lines if line.startswith('KEY=')]
        statuses = dict(line.split('=', 1) for line in lines if not line.startswith('KEY='))
        expected = sorted(KEYS, key=lambda k: k.encode(mode))
        if order != expected or statuses != {'DUPLICATE': '22', 'EOF': '10', 'RANDOM': '00', 'REWRITE': '00', 'START': '00'}:
            raise AssertionError('mixed-key-indexed-probe-failed')
        results[mode] = dict(order=order, statuses=statuses, matches_cp037=order == EXPECTED_CP037,
                             source_sha256=sha(source.read_bytes()), helper_sha256=sha(key_source.read_bytes()))
    if not results['cp037']['matches_cp037'] or results['ascii']['matches_cp037']:
        raise AssertionError('fixture-does-not-discriminate-storage-order')
    return receipt(output / 'mixed-key-probe.json', phase='mixed-key-indexed-probe', keys=KEYS,
                   expected_cp037=EXPECTED_CP037, results=results, decimal_key_restriction_retained=True,
                   scope='Mixed four-byte keys using actual LYKEY and indexed storage; not business reconciliation or z/OS confirmation',
                   zos_confirmed=False, model_calls=0)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    probe(p.parse_args().output)
