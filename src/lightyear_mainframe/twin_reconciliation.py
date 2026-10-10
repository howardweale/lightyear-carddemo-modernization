"""Public three-way diagnostics; no adjudication, approvals or evidence admission."""
from itertools import combinations
from pathlib import Path
import json
import os
import shutil
from .legacy_twin import (ROOT, PUBLIC_SCENARIOS, FILES, FLAGS, build, run, sha,
                          public_inputs, receipt, execute, linux_platform, new_output)
from .records import load_copybook, from_ascii_fixed
from .zos_bindings import load_bindings, dataset_binding
from carddemo_oracle.oracle import run_intcalc, OracleExecutionError
from carddemo_oracle.records import Account, CardXref, CategoryBalance, Disclosure, write_records

JAVA_RUNNER = """import java.nio.file.*;
import ai.lightyear.carddemo.codec.CardDemoRecordCodec;
import ai.lightyear.carddemo.service.InterestCalculationService;
public class TwinCandidate {
 public static void main(String[] a) throws Exception {
  Path p=Path.of(a[0]);
  var r=new InterestCalculationService().calculate(
   Files.readAllLines(p.resolve("TCATBALF")).stream().map(CardDemoRecordCodec::parseCategoryBalance).toList(),
   Files.readAllLines(p.resolve("DISCGRP")).stream().map(CardDemoRecordCodec::parseDisclosure).toList(),
   Files.readAllLines(p.resolve("XREFFILE")).stream().map(CardDemoRecordCodec::parseCardXref).toList(),
   Files.readAllLines(p.resolve("ACCTFILE")).stream().map(CardDemoRecordCodec::parseAccount).toList(), a[2],a[3],"source-faithful");
  Path out=Path.of(a[1]);
  Files.write(out.resolve("ACCTFILE"),r.accounts().stream().map(CardDemoRecordCodec::renderAccount).toList());
  Files.write(out.resolve("TRANSACT"),r.transactions().stream().map(CardDemoRecordCodec::renderTransaction).toList());
 }
} """


def compare_images(left, right, layout, keys):
    """Report raw AND decoded differences, including filler, signs and timestamps."""
    def index(raw):
        records = from_ascii_fixed(layout, raw)
        indexed = {}
        for n, record in enumerate(records):
            fields = {f['path']: f for f in record['fields']}
            key = tuple(fields[p]['value'] for p in keys) if keys else (n,)
            if key in indexed:
                raise ValueError('duplicate comparison key')
            indexed[key] = fields
        return indexed
    a, b = index(left), index(right)
    differences = {}
    for key in a.keys() & b.keys():
        for path in a[key]:
            x, y = a[key][path], b[key][path]
            if x['raw_hex'] != y['raw_hex'] or x['value'] != y['value']:
                d = differences.setdefault(path, dict(raw_records=0, value_records=0, filler=x['filler']))
                d['raw_records'] += x['raw_hex'] != y['raw_hex']
                d['value_records'] += x['value'] != y['value']
    return dict(byte_identical=left == right, keyed_identical=not differences and a.keys()==b.keys(),
                added=len(b.keys()-a.keys()), deleted=len(a.keys()-b.keys()),
                order_or_framing_only=left != right and not differences and a.keys()==b.keys(),
                fields=differences, left_sha256=sha(left), right_sha256=sha(right))


def compile_java(output):
    output.mkdir()
    (output/'classes').mkdir()
    base = ROOT/'candidate-java/src/main/java/ai/lightyear/carddemo'
    sources = [base/p for p in ('service/InterestCalculationService.java', 'codec/CardDemoRecordCodec.java',
                                'codec/ZonedDecimal.java', 'domain/Records.java')]
    (output/'TwinCandidate.java').write_text(JAVA_RUNNER)
    (output/'Service.java').write_text('package org.springframework.stereotype; public @interface Service {}')
    generated = [output/'TwinCandidate.java', output/'Service.java']
    javac = str(Path(os.environ['JAVA_HOME'])/'bin/javac')
    version = execute([javac, '-version'], output, output/'version').stdout.decode().strip()
    if not version.startswith('javac 21.'):
        raise ValueError('Java 21 is required')
    execute([javac, '-d', output/'classes', *sources, *generated], output, output/'compile')
    return dict(compiler=version, sources={p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sources},
                adapters={p.name: sha(p.read_bytes()) for p in generated})


def reference(meta, images, folder):
    folder.mkdir()
    def parsed(dd, cls):
        return [cls.parse(s) for s in images[dd].decode('ascii').splitlines()]
    try:
        r = run_intcalc(parsed('TCATBALF', CategoryBalance), parsed('DISCGRP', Disclosure),
                        parsed('XREFFILE', CardXref), parsed('ACCTFILE', Account),
                        meta['processing_date'], meta['candidate_timestamp'], 'source-faithful')
    except OracleExecutionError as e:
        (folder/'failure.txt').write_text(str(e))
        return dict(status='execution-failure', diagnostic_sha256=sha(str(e).encode()))
    write_records(folder/'ACCTFILE', (r.render() for r in r.accounts), 300)
    write_records(folder/'TRANSACT', (r.render() for r in r.transactions), 350)
    return dict(status='completed')


def probes(output):
    output.mkdir()
    src = ROOT/'tools/legacy_twin/platform-probe.cob'
    execute(['cobc','-x','-free',*FLAGS,src,'-o',output/'probe'], output, output/'compile')
    result = execute([output/'probe'], output, output/'run', extra_env={'COB_CURRENT_DATE':'2022/07/18 00:00:00.000000000'})
    observed = dict(line.split('=',1) for line in result.stdout.decode().splitlines())
    expected = {'SIGNED-DISPLAY':'0012345-', 'SIGNED-STORAGE':'001234N','ROUNDED':'-001.24','TRUNCATED':'-001.23','SIZE-TRUNCATION':'23',
                'COLLATION':'A-before-a','LEAP-DATE':'20240229','CLOCK':'2022071800000000',
                'MISSING-FILE':'35','DUPLICATE-KEY':'22','MISSING-KEY':'23','EOF':'10'}
    packed = (output/'packed.bin').read_bytes().hex()
    summary = receipt(output/'probes.json', phase='platform-probes', source_sha256=sha(src.read_bytes()),
                      observed=observed, expected_gnucobol=expected, packed_hex=packed,
                      zos_match='unknown-for-all-probes',
                      limitation='No authorised Enterprise COBOL runtime baseline supplied; no z/OS confirmation inferred')
    if observed != expected or packed != '0012345c0012345d':
        raise AssertionError('platform probe changed; preserved actual observations')
    return summary


def reconcile(output):
    linux_platform()
    output = new_output(output)
    build(output/'twin')
    java = compile_java(output/'java')
    bindings = load_bindings()
    rows = []
    for scenario in PUBLIC_SCENARIOS:
        job, meta, images, _ = public_inputs(scenario)
        folder = output/scenario
        folder.mkdir()
        twin = run(output/'twin', scenario, folder/'twin')
        if job != 'INTCALC':
            rows.append(dict(scenario=scenario, twin_returncode=twin['returncode'], status='not-three-way-supported',
                classification='missing-reference-and-candidate',
                reason='Existing Python and Java implement INTCALC only; do not invent POSTTRAN oracle results'))
            continue
        (folder/'inputs').mkdir()
        for dd, raw in images.items():
            (folder/'inputs'/dd).write_bytes(raw)
        py = reference(meta, images, folder/'python')
        (folder/'java').mkdir()
        candidate = execute([str(Path(os.environ['JAVA_HOME'])/'bin/java'),'-cp',output/'java/classes','TwinCandidate',folder/'inputs',folder/'java',
                             meta['processing_date'],meta['candidate_timestamp']], folder, folder/'java/run', allowed=(0,1))
        states = {'twin': 'completed' if twin['returncode']==0 else 'execution-failure',
                  'python':py['status'], 'java':'completed' if candidate.returncode==0 else 'execution-failure'}
        row = dict(scenario=scenario, states=states, comparisons={})
        if set(states.values()) == {'execution-failure'}:
            # Same broad class alone is insufficient: check the source-specific diagnostic too.
            logs = [(folder/'twin/logs/program.stdout').read_text(),
                    (folder/'python/failure.txt').read_text(), (folder/'java/run.stderr').read_text()]
            matched = 'ERROR READING DEFAULT DISCLOSURE GROUP' in logs[0] and all('DEFAULT DISCLOSURE MISSING' in x for x in logs[1:])
            row.update(status='expected-failure-agreement' if matched else 'unresolved-failure-diagnostics',
                       classification='missing-disclosure-source-path' if matched else 'unresolved')
        elif set(states.values()) != {'completed'}:
            row.update(status='execution-disagreement', classification='unresolved')
        else:
            paths = {'twin':folder/'twin/after', 'python':folder/'python', 'java':folder/'java'}
            for left,right in combinations(paths,2):
                d = {}
                for dd in ('ACCTFILE','TRANSACT'):
                    binding = dataset_binding(bindings,'INTCALC','STEP15',dd)
                    layout = load_copybook(ROOT/binding['copybook'])
                    d[dd] = compare_images((paths[left]/dd).read_bytes(),(paths[right]/dd).read_bytes(),layout,binding['keys'])
                row['comparisons'][left+'-vs-'+right] = d
            equal = all(d['byte_identical'] for pair in row['comparisons'].values() for d in pair.values())
            row.update(status='byte-agreement' if equal else 'disagreement', classification='none' if equal else 'unresolved')
        rows.append(row)
    platform_results = probes(output/'platform')
    from carddemo_oracle import oracle, records
    report = receipt(output/'reconciliation.json', phase='three-way-reconciliation', scenarios=rows,
                     java=java, reference_sources={Path(m.__file__).name: sha(Path(m.__file__).read_bytes()) for m in (oracle,records)},
                     platform_probes_sha256=platform_results['content_sha256'],
                     status='engineering-report-not-release-gate', default_oracle_changed=False)
    lines = ['# Public three-way reconciliation', '', '| Scenario | Observation | Classification |', '|---|---|---|']
    lines += [f'| {r["scenario"]} | {r["status"]} | {r["classification"]} |' for r in rows]
    lines += ['', 'All raw outputs, field differences and source hashes are retained in this artifact.',
              'No timestamp, filler, numeric sign or record-order discrepancy is suppressed.',
              'No z/OS confirmation, qualification or measurement credit. Unresolved differences block oracle promotion.']
    (output/'reconciliation.md').write_text('\n'.join(lines)+'\n')
    return report


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path)
    reconcile(p.parse_args().output)
