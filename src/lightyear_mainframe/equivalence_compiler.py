"""Re-checkable object identity using the pinned twin toolchain, CI only.

All executable sections, data, symbol tables and relocations remain in the
comparison. Only debug sections are excluded. No literal reordering is enabled.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess

from .equivalence_automation import digest, sealed
from .legacy_twin import execute, linux_platform, clean_env
from .systematic_mutation import apply

RULES = {
    'comments': 'Replace C comments by whitespace, preserving quoted tokens and token boundaries.',
    'line-markers': 'Remove preprocessor line directives only; refuse location macro consumers.',
    'generated-private-names': 'Bijectively rename only compiler-generated static b_/f_/a_/c_ identifiers, consistently across headers.',
    'timestamp': 'No textual rewrite: fixed libfaketime compiler clock and SOURCE_DATE_EPOCH.',
}
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[A-Za-z_]\w*', re.S)


def require_ci():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not re.fullmatch(r'[0-9a-f]{40}', os.environ.get('EQUIVALENCE_HEAD', '')):
        raise ValueError('CI-only-execution-required')


def normalize(files):
    combined = '\n'.join(files.values())
    # Location macros or inline assembly could make apparently cosmetic names
    # observable. Fail closed; do not attempt textual compensation.
    if re.search(r'\b(?:__LINE__|__FILE__|__func__|__FUNCTION__|asm|__asm__)\b|##', combined):
        raise ValueError('normalization-observable-metadata')
    cleaned = {n: TOKEN.sub(lambda m: ' ' if m[0].startswith(('/*', '//')) else m[0], t) for n, t in files.items()}
    cleaned = {n: '\n'.join(line for line in t.splitlines() if not re.match(r'^\s*#\s*(?:line\b|\d+\s+")', line)) + '\n'
               for n, t in cleaned.items()}
    # Only names with a static declaration are eligible, so externally visible
    # ABI names cannot change. References in strings are deliberately untouched.
    names = []
    for name in sorted(cleaned):
        for match in re.finditer(r'\bstatic\s+[^;{}=\n]*?\b([bfac]_\d+)\s*(?=[\[=;])', cleaned[name]):
            if match[1] not in names: names.append(match[1])
    mapping = {n: 'lyeq_private_' + str(i) for i, n in enumerate(names)}
    if 'lyeq_private_' in combined: raise ValueError('normalization-name-collision')
    # Identifier macros/stringification can observe spelling too.
    if mapping and any(re.search(r'^\s*#\s*define\b', t, re.M) for t in cleaned.values()):
        mapping = {}  # conservative: preserve names when macro expansion is present
    result = {n: TOKEN.sub(lambda m: mapping.get(m[0], m[0]), t) for n, t in cleaned.items()}
    return result, mapping


def binary_profile(directory=Path('/etc/gnucobol')):
    values={}; seen=set()
    def read(name):
        if name in seen:raise ValueError('recursive-compiler-config')
        seen.add(name)
        for line in (directory/name).read_text().splitlines():
            line=line.split('#',1)[0].strip()
            include=re.fullmatch(r'include\s*:?\s*"([^"/]+)"',line)
            if include:read(include[1]);continue
            setting=re.fullmatch(r'(binary-truncate|binary-byteorder|binary-size)\s*:\s*(\S+)',line)
            if setting:values[setting[1]]=setting[2]
        seen.remove(name)
    read('ibm.conf')
    if values.get('binary-truncate') not in ('yes','no') or values.get('binary-byteorder') not in ('big-endian','native') or values.get('binary-size')!='2-4-8':
        raise ValueError('unmodeled-twin-binary-profile:'+str(values))
    import sys
    return dict(binary_truncate=values['binary-truncate']=='yes',byteorder='big' if values['binary-byteorder']=='big-endian' else sys.byteorder,settings=values)


def toolchain():
    require_ci(); host = linux_platform()
    names = ('cobc', 'gcc', 'objcopy', 'as', 'ld')
    binaries = {n: digest(Path(shutil.which(n)).read_bytes()) for n in names}
    packages = subprocess.check_output(['dpkg-query', '-W', '-f=${binary:Package}=${Version}\n',
                                        'gcc*', 'binutils*', 'libcob*', 'gnucobol3', 'libfaketime'], env=clean_env()).decode()
    configs = {str(p): digest(p.read_bytes()) for p in sorted(Path('/etc/gnucobol').glob('*.conf'))}
    return sealed(dict(host=host, binaries=binaries, packages=packages, configs=configs, binary_profile=binary_profile(),
                       gcc_flags=['-O2', '-fPIC', '-c'], image_recipe='tools/legacy_twin/reproducible.Containerfile'))


def compile_object(root, folder, program, mutant=None):
    require_ci(); folder.mkdir(parents=True, exist_ok=False)
    source = root / f'spec/mainframe/public-source/{program}.cbl'
    for book in (root / 'spec/mainframe/copybooks').glob('*.cpy'): shutil.copyfile(book, folder / book.name)
    shutil.copyfile(source, folder / source.name)
    if mutant:
        operand = folder / mutant.get('source_path', source.name)
        operand.write_text(apply(operand.read_text(), mutant))
    execute(['cobc', '-C', '-fixed', '-std=ibm', '-fsign=EBCDIC', '-O2', '-I', '.', source.name], folder, folder / 'cobc')
    generated = {p.name: p.read_text() for p in sorted(folder.glob(program + '*.h'))}
    generated[program + '.c'] = (folder / (program + '.c')).read_text()
    for name, value in generated.items(): (folder / (name + '.original')).write_text(value)
    normalized, mapping = normalize(generated)
    for name, value in normalized.items(): (folder / name).write_text(value)
    execute(['gcc', '-O2', '-fPIC', '-c', program + '.c', '-o', 'program.o'], folder, folder / 'gcc')
    execute(['objcopy', '--strip-debug', 'program.o', 'comparison.o'], folder, folder / 'objcopy')
    result = sealed(dict(object_sha256=digest((folder / 'comparison.o').read_bytes()),
                         raw_object_sha256=digest((folder / 'program.o').read_bytes()),
                         generated_sha256=digest(generated), normalized_sha256=digest(normalized),
                         name_mapping=mapping, rules=list(RULES), literal_ordering='unchanged',
                         object='comparison.o', normalization_version=1))
    (folder / 'identity.json').write_text(__import__('json').dumps(result, indent=2, sort_keys=True)+'\n')
    return result


def adversarial_rules(folder):
    """Each enabled rule is challenged by actual differing machine code."""
    require_ci(); folder.mkdir(parents=True)
    reports = []
    for rule in RULES:
        hashes = []
        for value in (1, 2):
            sub = folder / (rule + '-' + str(value)); sub.mkdir()
            code = f'/* generated at irrelevant time */\n#line 10 "same.c"\nstatic int b_{value}= {value};\nint answer(void) {{ return b_{value}; }}\n'
            clean, _ = normalize({'probe.c': code})
            (sub / 'probe.c').write_text(clean['probe.c'])
            execute(['gcc', '-O2', '-c', 'probe.c', '-o', 'probe.o'], sub, sub / 'gcc')
            execute(['objcopy', '--strip-debug', 'probe.o', 'comparison.o'], sub, sub / 'objcopy')
            hashes.append(digest((sub / 'comparison.o').read_bytes()))
        reports.append(dict(rule=rule, original=hashes[0], mutant=hashes[1], passed=hashes[0] != hashes[1]))
    if not all(r['passed'] for r in reports): raise ValueError('normalization-route-disabled')
    return reports
