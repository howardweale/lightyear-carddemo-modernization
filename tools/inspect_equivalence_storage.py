"""CI storage diagnostics; no equivalence or whole-program acceptance claims."""
import argparse
import json
from pathlib import Path
from lightyear_mainframe.equivalence_automation import bound, digest, sealed
from lightyear_mainframe.equivalence_storage import storage_ir
from lightyear_mainframe.equivalence_compiler import require_ci


# Exact committed spellings: never infer a suffix on case-insensitive hosts.
PROGRAM_PATHS = {
    'CBACT04C': 'spec/mainframe/public-source/CBACT04C.cbl',
    'CBTRN02C': 'spec/mainframe/public-source/CBTRN02C.cbl',
    'CBTRN03C': 'spec/mainframe/public-source/CBTRN03C.cbl',
    'CBSTM03A': 'spec/mainframe/public-source/CBSTM03A.CBL',
    'CBSTM03B': 'spec/mainframe/public-source/CBSTM03B.CBL',
}

def inspect(root, output):
    require_ci()
    output.mkdir(parents=True, exist_ok=False)
    books = {p.stem: bound(p.relative_to(root).as_posix(), p.read_bytes().decode())
             for p in sorted((root/'spec/mainframe/copybooks').glob('*.cpy'))}
    reports = []
    # TRANREPT is the logical name of CBTRN03C, not a second independent program.
    for program, source in [('INTCALC','CBACT04C'), ('POSTTRAN','CBTRN02C'),
                            ('TRANREPT/CBTRN03C','CBTRN03C'), ('CBSTM03A','CBSTM03A'), ('CBSTM03B','CBSTM03B')]:
        path = root / PROGRAM_PATHS[source]
        raw = path.read_bytes()
        result = storage_ir(bound(path.relative_to(root).as_posix(), raw.decode()), books)
        repeated = storage_ir(bound(path.relative_to(root).as_posix(), raw.decode()), books)
        if repeated != result:
            raise ValueError('non-deterministic-storage-translation')
        (output/(source+'.json')).write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
        reports.append(dict(program=program, source_sha256=digest(raw),
            source_path=PROGRAM_PATHS[source], unsupported_count=len(result['unsupported']),
            area_count=len(result['areas']), view_count=sum(len(a['views']) for a in result['areas']),
            unsupported=result['unsupported'], deterministic=True,
            whole_program_accepted=False, differential_inputs_completed=0))
    (output/'summary.json').write_text(json.dumps(sealed(dict(stage='E2-storage-foundation',
        programs=reports, resolution_credit=0, model_calls=0)), indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
    a = p.parse_args(); inspect(Path.cwd(), a.output)
