"""Reject invalid UTF-8 and known mojibake sequences in tracked service Java."""
import argparse
from pathlib import Path
import subprocess

MARKERS = ('\u00e2\u20ac', '\u00c3\u00a2', '\ufffd')


def check_text(raw, name):
    text = raw.decode('utf-8')
    for number, line in enumerate(text.splitlines(), 1):
        if any(marker in line for marker in MARKERS):
            raise ValueError('java-mojibake:' + name + ':' + str(number))


def check(root):
    root = Path(root)
    names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--',
        'factory/carddemo-web/service/**/*.java']).decode('utf-8').split('\0')
    paths = [name for name in names if name]
    if not paths:
        raise ValueError('java-source-inventory-empty')
    for name in paths:
        check_text((root / name).read_bytes(), name)
    return len(paths)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    print('Java UTF-8/mojibake check passed:', check(args.root), 'tracked files')
