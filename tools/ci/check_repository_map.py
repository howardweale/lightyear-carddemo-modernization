"""Check maintained navigation and preserved history without network access."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

DOCUMENTS = ('README.md', 'ARCHITECTURE.md', 'CONTRIBUTING.md', 'docs/index.md')
ARCHIVE = 'docs/history/README-history-2026-10-17.md'
SOURCE = '9343791b0776a1a6b1636ab47c0c2443dad45217'
LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


def check(root):
    root = Path(root).resolve()
    failures = []
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
    original = subprocess.check_output(['git', 'show', SOURCE + ':README.md'], cwd=root)
    archived = (root / ARCHIVE).read_bytes()
    if archived != original:
        failures.append('historical README bytes differ from source commit')
    if (root / 'CHANGELOG.md.rej').exists():
        failures.append('stray CHANGELOG.md.rej remains')
    if failures:
        raise ValueError('\n'.join(failures))
    return {'documents': len(DOCUMENTS), 'archive_sha256': hashlib.sha256(archived).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    print(check(parser.parse_args().root))
