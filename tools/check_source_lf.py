"""Reject changed source CRLF and invalid/misencoded Markdown; never rewrite evidence."""
import argparse
from pathlib import Path
import subprocess


def check_paths(root, names):
    bad = []
    for name in names:
        path = Path(name)
        if path.suffix.lower() == '.md':
            raw = (Path(root)/path).read_bytes()
            try:
                text = raw.decode('utf-8', errors='strict')
            except UnicodeDecodeError as exc:
                raise ValueError('markdown-not-utf8: ' + name) from exc
            if text.encode('utf-8') != raw:
                raise ValueError('markdown-utf8-roundtrip: ' + name)
            # Valid UTF-8 can still contain a second encoding of an old en dash.
            if any(marker in text for marker in ('\u00c3\u00a2', '\u00e2\u20ac', '\u00c3\u0192', '\ufffd')):
                raise ValueError('markdown-mojibake: ' + name)
        if path.parts and path.parts[0] in {'src', 'tools'} and path.suffix in {'.py', '.java'}:
            if b'\r\n' in (Path(root)/path).read_bytes():
                bad.append(name)
    if bad:
        raise ValueError('source-crlf: ' + ', '.join(bad))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    names = subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=ACMR',
                                     '-z', args.base, 'HEAD']).decode().split('\0')
    check_paths(Path.cwd(), [name for name in names if name])


if __name__ == '__main__': main()
