"""Byte-backed storage for E2; separate from the historical field-only IR.

Unknown bytes stay unknown. No COBOL numeric conversion, program interpretation
or equivalence authority is implied by successfully constructing a layout.
"""
from dataclasses import dataclass, asdict
import re
from .records import compile_copybook, LayoutError
from .equivalence_automation import sealed


class StorageError(ValueError):
    pass


@dataclass(frozen=True)
class View:
    path: str
    area: str
    offset: int
    length: int
    picture: str | None
    usage: str
    group: bool
    source: dict


# Local E2 resource budget, not an Enterprise COBOL language maximum.
AREA_LIMITS = {'FD': 32760, 'WORKING-STORAGE': 16*1024*1024, 'LINKAGE': 16*1024*1024, 'LOCAL-STORAGE': 16*1024*1024}


def compile_area(name, declarations, *, kind='WORKING-STORAGE'):
    """Compile a bound series of 01 declarations as views of one byte area.

    A synthetic containing group permits legal level-01 OCCURS/REDEFINES
    without weakening the existing record decoder's public contract. Unknown
    clauses and variable layouts remain explicitly unsupported.
    """
    if kind not in AREA_LIMITS:
        raise StorageError('unsupported-storage-kind:' + kind)
    if not declarations:
        raise StorageError('empty-storage-area')
    words = ['01', 'LY-AREA', '.']
    locations = {}
    for serial, declaration in enumerate(declarations):
        values = [t.text for t in declaration]
        if values[-1:] == ['.']:
            values.pop()
        if len(values) < 2 or not values[0].isdigit():
            raise StorageError('expected-data-declaration')
        level = int(values[0])
        if level == 88:
            # Conditions have no storage, but are retained by the caller for
            # executable translation. Do not pretend to evaluate them here.
            continue
        if level == 77:
            values[0] = '02'
        elif 1 <= level < 49:
            values[0] = f'{level+1:02d}'
        else:
            raise StorageError('unsupported-storage-level:' + values[0])
        original = values[1]
        # Anonymous overlays are legal; make their internal path unambiguous.
        if original == 'FILLER':
            values[1] = f'LY-FILLER-{serial}'
        locations[len(words)+1] = declaration[0].location()
        words.extend(values + ['.'])
    layout = compile_copybook('\n'.join('       ' + word for word in words),
                              max_length=AREA_LIMITS[kind], storage_overlays=True)
    if layout.variable:
        raise StorageError('ODO-active-length-not-yet-interpreted')
    views = []

    def alternatives(node):
        groups = []
        for child in node.children:
            if child.redefines:
                if not groups or child.redefines not in {n.name for n in groups[-1]}:
                    raise StorageError('invalid-overlay-target')
                groups[-1].append(child)
            else:
                groups.append([child])
        return groups

    def emit(node, prefix, offset):
        for index in range(node.occurs):
            start = offset + index * node.width
            path = prefix + node.name + (f'[{index+1}]' if node.occurs > 1 else '')
            if node.name != 'LY-AREA':
                views.append(View(path, name, start, node.width, node.picture, node.usage,
                                  node.picture is None, locations[node.line]))
            child_offset = start
            for siblings in alternatives(node):
                for child in siblings:
                    emit(child, '' if node.name == 'LY-AREA' else path + '.', child_offset)
                child_offset += (max(child.width * child.occurs for child in siblings) if node.name == 'LY-AREA'
                                 else siblings[0].width * siblings[0].occurs)

    emit(layout.tree, '', 0)
    if len({v.path for v in views}) != len(views):
        raise StorageError('duplicate-qualified-storage-view')
    return sealed(dict(schema='cobol-byte-area/1', name=name, kind=kind, length=layout.record_length,
        views=[asdict(v) for v in views], declarations=[
            dict(tokens=[t.text for t in d], location=d[0].location()) for d in declarations],
        initialization='explicitly-uninitialized-until-COBOL-values-applied',
        numeric_semantics='PIC/USAGE views only; conversion requires validated interpreter'))


class Memory:
    """Byte operations with alias identity, overlap snapshots and knownness."""
    def __init__(self, areas):
        from .equivalence_automation import verify
        self.buffers = {}
        self.known = {}
        self.views = {}
        for area in areas:
            verify(area)
            name = area['name']; length = area['length']
            kind = area.get('kind', 'FD')  # Old records retain the conservative record limit.
            if kind not in AREA_LIMITS or name in self.buffers or type(length) is not int or not 0 <= length <= AREA_LIMITS[kind]:
                raise StorageError('invalid-or-duplicate-area')
            self.buffers[name] = bytearray(length)
            self.known[name] = bytearray(length)
            for raw in area['views']:
                view = View(**raw)
                key = name + ':' + view.path
                if (key in self.views or view.area != name or view.offset < 0
                        or view.length < 0 or view.offset + view.length > length):
                    raise StorageError('invalid-or-duplicate-view')
                self.views[key] = view

    def view(self, name):
        if name not in self.views:
            raise StorageError('unbound-qualified-view:' + name)
        return self.views[name]

    def read(self, name):
        v = self.view(name); stop = v.offset + v.length
        if not all(self.known[v.area][v.offset:stop]):
            raise StorageError('uninitialized-byte-read:' + name)
        return bytes(self.buffers[v.area][v.offset:stop])

    def write(self, name, value):
        v = self.view(name)
        if not isinstance(value, bytes) or len(value) != v.length:
            raise StorageError('exact-byte-write-required')
        self.buffers[v.area][v.offset:v.offset+v.length] = value
        self.known[v.area][v.offset:v.offset+v.length] = b'\x01' * v.length

    def group_move(self, source, destination, *, space=b' '):
        target = self.view(destination)
        if not self.view(source).group or not target.group or len(space) != 1:
            raise StorageError('group-move-requires-groups-and-codec-space')
        # Reading a snapshot before writing preserves overlapping aliases.
        value = self.read(source)
        self.write(destination, value[:target.length].ljust(target.length, space))

    def overlaps(self, first, second):
        a, b = self.view(first), self.view(second)
        return a.area == b.area and max(a.offset, b.offset) < min(a.offset+a.length, b.offset+b.length)


def storage_ir(program, copybooks):
    """Translate bound DATA declarations, preserving every unsupported location.

    This is a storage acceptance report, not the whole-program E2 gate. File
    status effects, CFG, arithmetic and application interpretation are separate.
    """
    bindings = {}; issues = []; areas = []; declarations = []; area = None; section = None

    def expand(source, active=()):
        if source.path in active:
            raise StorageError('recursive-copybook')
        bindings[source.path] = source.sha256
        tokens = source.tokens(); result = []; i = 0
        while i < len(tokens):
            if tokens[i].text != 'COPY':
                result.append(tokens[i]); i += 1; continue
            end = next((j for j in range(i+1,len(tokens)) if tokens[j].text == '.'), len(tokens))
            name = tokens[i+1].text.strip("'\"") if i+1 < len(tokens) else ''
            if end != i+2 or name not in copybooks:
                issues.append(dict(reason='unbound-or-qualified-COPY', **tokens[i].location()))
            else:
                result.extend(expand(copybooks[name], active+(source.path,)))
            i = end+1
        return result

    def flush():
        if declarations:
            try:
                areas.append(compile_area(area, declarations, kind='FD' if section.startswith('FD:') else section))
            except (StorageError, LayoutError) as error:
                issues.append(dict(reason=str(error), area=area, **declarations[0][0].location()))
            declarations.clear()

    tokens = expand(program)
    active = False; current = []; previous_line = None
    def finish():
        if current:
            declarations.append(list(current)); current.clear()

    for i, token in enumerate(tokens):
        pair = [t.text for t in tokens[i:i+2]]
        if pair == ['PROCEDURE', 'DIVISION']:
            finish(); flush(); break
        if pair == ['DATA', 'DIVISION']:
            active = True
        if not active:
            continue
        if token.text == 'FD' or pair[1:] == ['SECTION']:
            finish(); flush()
            area = ('FD:' + tokens[i+1].text if token.text == 'FD' else token.text)
            section = area
        line = (token.path, token.line)
        is_level = (line != previous_line and re.fullmatch(r'[0-9]{2}', token.text)
                    and 1 <= int(token.text) <= 88)
        if is_level:
            finish()
            if token.text in ('01', '77') and tokens[i+2:i+3] and tokens[i+2].text != 'REDEFINES':
                if section and not section.startswith('FD:'):
                    flush()
                    area = section + ':' + tokens[i+1].text
                elif declarations:
                    # Multiple FD 01 descriptions share a record area implicitly;
                    # concatenating them would invent incorrect byte offsets.
                    issues.append(dict(reason='multiple-FD-record-alternatives-not-yet-translated',
                                       **token.location()))
            if area is None:
                issues.append(dict(reason='data-outside-storage-area', **token.location()))
            current.append(token)
        elif current:
            current.append(token)
        previous_line = line
    return sealed(dict(schema='cobol-byte-storage-ir/1', bindings=bindings, areas=areas,
        unsupported=issues, storage_complete=not issues, whole_program_accepted=False,
        remaining_gates=['whole-program CFG/effects', 'numeric encoders', '1000-input differential twin comparison']))
