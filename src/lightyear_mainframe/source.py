"""Fixed-format source reader; locations survive COPY expansion.

This is a source inventory lexer, not a compiler or a control-flow prover.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from pathlib import Path


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    path: str
    line: int
    column: int
    inclusion: tuple[str, ...] = ()

    def location(self):
        return dict(path=self.path, line=self.line, column=self.column,
                    inclusion=list(self.inclusion))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_text(text: str):
    """Return code and a per-character physical location map.

    Column 7 comments are excluded; columns 73+ are sequence metadata. Literal
    continuation removes the opening delimiter on the continuation line. Tabs use explicit eight-column stops. Debug
    lines and compiler directives are refused instead of silently choosing a mode.
    """
    chars, locations = [], []
    quote = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        line = line.expandtabs(8)
        indicator = line[6:7]
        if indicator in ('*', '/'):
            continue
        if indicator not in (' ', '-', ''):
            raise SourceError(f'line {number}: unsupported indicator {indicator!r}')
        code = line[7:72]
        if code.lstrip().startswith(('>>', 'CBL ', 'PROCESS ')):
            raise SourceError(f'line {number}: compiler directive requires preprocessing')
        offset = 8
        if indicator == '-':
            n = len(code) - len(code.lstrip())
            code, offset = code[n:], offset + n
            if quote:
                if not code.startswith(quote):
                    raise SourceError(f'line {number}: invalid literal continuation')
                code, offset = code[1:], offset + 1
        else:
            if quote:
                raise SourceError(f'line {number}: unterminated literal')
            chars.append(' '); locations.append((number, 7))
        i = 0
        while i < len(code):
            ch = code[i]
            if not quote and code[i:i+2] == '*>':
                break
            chars.append(ch); locations.append((number, offset+i))
            if ch in "'\"":
                if quote == ch and code[i+1:i+2] == ch:
                    i += 1
                    chars.append(ch); locations.append((number, offset+i))
                elif quote == ch:
                    quote = None
                elif quote is None:
                    quote = ch
            i += 1
    if quote:
        raise SourceError('unterminated literal at end of source')
    return ''.join(chars), locations


LEX = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|==|[A-Za-z0-9_-]+(?:\.[0-9]+)?|[^\s]", re.S)


def tokenize(text: str, path: str = '<memory>') -> list[Token]:
    code, locations = fixed_text(text)
    return [Token(m.group() if m.group()[0] in "'\"" else m.group().upper(),
                  path, *locations[m.start()]) for m in LEX.finditer(code)]


class Corpus:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.files = sorted(p for p in self.root.rglob('*')
                            if p.is_file() and p.suffix.lower() in ('.cbl', '.cob', '.cpy'))
        self.hashes = {p.relative_to(self.root).as_posix(): sha(p.read_bytes()) for p in self.files}
        self.copies: dict[str, list[Path]] = {}
        for p in self.files:
            if p.suffix.lower() == '.cpy':
                self.copies.setdefault(p.stem.upper(), []).append(p)
        self.references, self.issues = [], []

    def issue(self, token, cause, **details):
        self.issues.append(dict(cause=cause, **token.location(), **details))

    def expand(self, path: Path, inclusion=(), ancestors=()):
        relative = path.relative_to(self.root).as_posix()
        if relative in ancestors:
            raise SourceError(f'recursive COPY: {relative}')
        tokens = [replace(t, inclusion=inclusion) for t in tokenize(path.read_text(), relative)]
        out, i = [], 0
        while i < len(tokens):
            t = tokens[i]
            if t.text == 'REPLACE':
                raise SourceError(f'{relative}:{t.line}: standalone REPLACE requires preprocessing')
            if t.text != 'COPY':
                out.append(t); i += 1; continue
            end = next((j for j in range(i+1, len(tokens)) if tokens[j].text == '.'), None)
            if end is None or end <= i+1:
                raise SourceError(f'{relative}:{t.line}: malformed COPY')
            declaration = tokens[i+1:end]
            name = declaration[0].text.strip("'\"").upper()
            candidates = self.copies.get(name, [])
            ref = dict(**t.location(), name=name, candidates=[p.relative_to(self.root).as_posix() for p in candidates])
            self.references.append(ref)
            if len(candidates) != 1:
                self.issue(t, 'missing-copybook' if not candidates else 'ambiguous-copybook', name=name)
                i = end+1; continue
            chain = inclusion + (f'{relative}:{t.line}:{t.column}',)
            body = self.expand(candidates[0], chain, ancestors+(relative,))
            tail = declaration[1:]
            if tail:
                if tail[0].text != 'REPLACING':
                    raise SourceError(f'{relative}:{t.line}: unsupported COPY qualifier')
                replacements, k = [], 1
                while k < len(tail):
                    # Bounded COPY REPLACING pseudo-text form used by CardDemo.
                    if tail[k].text != '==':
                        raise SourceError(f'{relative}:{t.line}: COPY replacement requires pseudo-text')
                    a = k+1
                    k = next((j for j in range(a, len(tail)) if tail[j].text == '=='), len(tail))
                    old = [x.text for x in tail[a:k]]
                    if [x.text for x in tail[k:k+3]] != ['==', 'BY', '==']:
                        raise SourceError(f'{relative}:{t.line}: malformed COPY replacement')
                    a = k+3
                    k = next((j for j in range(a, len(tail)) if tail[j].text == '=='), len(tail))
                    if k == len(tail) or not old:
                        raise SourceError(f'{relative}:{t.line}: unterminated COPY replacement')
                    replacements.append((old, [x.text for x in tail[a:k]])); k += 1
                replaced, k = [], 0
                while k < len(body):
                    match = next(((old, new) for old, new in replacements
                                  if [x.text for x in body[k:k+len(old)]] == old), None)
                    if match:
                        old, new = match
                        replaced.extend(replace(body[k], text=value) for value in new)
                        k += len(old)
                    else:
                        replaced.append(body[k]); k += 1
                body = replaced
            out.extend(body); i = end+1
        return out
