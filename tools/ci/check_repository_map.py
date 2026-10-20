"""Check maintained navigation and preserved history without network access."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit

DOCUMENTS = ('README.md', 'ARCHITECTURE.md', 'CONTRIBUTING.md', 'docs/index.md')
ARCHIVE = 'docs/history/README-history-2026-10-17.md'
SOURCE = '9343791b0776a1a6b1636ab47c0c2443dad45217'
LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


# Named paths use repository-root semantics. Explicit ./ and ../ references use
# the containing document, like Markdown links. Scan prose and code alike.
TOKEN = re.compile(r"(?<![\w./\\-])(?:[A-Za-z]:[\\/]|[\\/]{1,2}|\.\.?[\\/])?[A-Za-z0-9_.*/?\[\]-]+(?:[\\/][A-Za-z0-9_.*/?\[\]-]+)*[\\/]?(?::\d+(?:-\d+)?)?")
EXTENSION = re.compile(r"\.(?:md|rst|txt|json|jsonl|yaml|yml|toml|ini|cfg|py|ps1|sh|sql|xml|java|cbl|cpy|csv|tsv|svg|png|jpg|html|js|ts|tsx|css|lock|rej)$", re.IGNORECASE)
URL = re.compile(r"(?:https?://|mailto:)[^\s<>`]+", re.IGNORECASE)
ROOT_NAMES = {'LICENSE', 'NOTICE', 'Dockerfile', 'Makefile'}


def named_paths(text, roots):
    # Link targets have their own document-relative validation. Retain labels so
    # an independently named path in a label is still checked as a root path.
    text = LINK.sub(lambda match: match.group(0).split('](', 1)[0].lstrip('!['), text)
    text = URL.sub('', text)
    code_spans = [m.span(1) for m in re.finditer(r'`+([^`]+)`+', text)]
    for match in TOKEN.finditer(text):
        in_code = any(start <= match.start() and match.end() <= end for start, end in code_spans)
        raw = re.sub(r':\d+(?:-\d+)?$', '', match.group(0)).rstrip('.,;:')
        value = raw.replace('\\', '/')
        first = value.split('/', 1)[0]
        if (value.startswith(('/', './', '../')) or re.match(r'^[A-Za-z]:/', value)
                or first in roots or value in ROOT_NAMES or value.endswith('/')
                or (in_code and '/' in value) or EXTENSION.search(value.rstrip('/'))):
            # Ordinary references to root directories must include a slash;
            # otherwise words such as "tools" in prose would become paths.
            if '/' in value or EXTENSION.search(value) or value in ROOT_NAMES:
                yield value


def named_target(root, document, raw):
    if raw.startswith('/') or re.match(r'^[A-Za-z]:/', raw):
        return False
    base = document.parent if raw.startswith(('./', '../')) else root
    parts = PurePosixPath(raw).parts
    wildcard = any(c in raw for c in '*?[')
    if wildcard:
        # A glob cannot introduce parent traversal or follow an escaping link.
        if '..' in parts:
            return False
        candidates = list(base.glob(raw))
        return bool(candidates) and all(p.resolve().is_relative_to(root) and p.exists() for p in candidates)
    target = (base / raw).resolve()
    return target.is_relative_to(root) and target.exists()


def check(root):
    root = Path(root).resolve()
    failures = []
    roots = {p.name for p in root.iterdir() if p.is_dir()}
    named_count = 0
    for name in DOCUMENTS:
        path = root / name
        text = path.read_text(encoding='utf-8')
        if name == 'README.md' and len(text.splitlines()) > 150:
            failures.append(name + ': more than 150 lines')
        for raw in LINK.findall(text):
            url = urlsplit(raw.strip('<>'))
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(root) or not target.exists():
                failures.append(name + ': missing or escaping link ' + raw)
        for raw in sorted(set(named_paths(text, roots))):
            named_count += 1
            if not named_target(root, path, raw):
                failures.append(name + ': missing or escaping named path ' + raw)
    original = subprocess.check_output(['git', 'show', SOURCE + ':README.md'], cwd=root)
    archived = (root / ARCHIVE).read_bytes()
    if archived != original:
        failures.append('historical README bytes differ from source commit')
    if (root / 'CHANGELOG.md.rej').exists():
        failures.append('stray CHANGELOG.md.rej remains')
    if failures:
        raise ValueError('\n'.join(failures))
    return {'documents': len(DOCUMENTS), 'named_paths': named_count, 'archive_sha256': hashlib.sha256(archived).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    print(check(parser.parse_args().root))
