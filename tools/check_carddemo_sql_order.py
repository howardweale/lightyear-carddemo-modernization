"""Fail closed on unreviewed SQL ordering in the CardDemo web slice.

Byte keys must lead with ebcdic_key. Only catalog-name listing and complete
JSON snapshot canonicalization are non-key exceptions. Dynamic ORDER BY
expressions are refused rather than guessed. This is a source lint, not a
PostgreSQL parser or a proof of query semantics.
"""
import argparse
from pathlib import Path
import re

ORDER=re.compile(r'\border\s+by\s*([^;"\n]*)',re.I)


def violations(text):
    failures=[]
    for match in ORDER.finditer(text):
        clause=match.group(1).strip()
        # Qualified identifiers retain the same physical key rule.
        key=re.match(r'(?:[A-Za-z_][A-Za-z_0-9]*\.)?ebcdic_key\b',clause,re.I)
        catalog=re.fullmatch(r'tablename(?:\s+(?:ASC|DESC))?',clause,re.I)
        snapshot=clause.lower().startswith('to_jsonb(t)::text)')
        if not (key or catalog or snapshot):
            failures.append(dict(line=text[:match.start()].count('\n')+1,clause=clause))
    return failures


def check(root):
    root=Path(root);failures=[]
    for path in sorted((root/'factory/carddemo-web').rglob('*')):
        if path.suffix not in {'.py','.java','.sql','.ts','.mjs'}:continue
        if any(part in {'target','node_modules','dist'} for part in path.parts):continue
        failures.extend(dict(path=path.relative_to(root).as_posix(),**row)
                        for row in violations(path.read_text(encoding='utf-8')))
    if failures:raise ValueError('carddemo-sql-order:'+repr(failures))
    return failures


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'))
    check(p.parse_args().root)
    print('CardDemo SQL ordering: byte keys first; catalog and snapshot exceptions only.')

if __name__=='__main__':main()
