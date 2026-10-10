"""Reject CRLF in newly changed source; never rewrite pinned historical files."""
import argparse
from pathlib import Path
import subprocess


def check_paths(root, names):
    bad = []
    for name in names:
        path = Path(name)
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
                                     '-z', args.base, 'HEAD', '--', 'src', 'tools']).decode().split('\0')
    check_paths(Path.cwd(), [name for name in names if name])


if __name__ == '__main__': main()
