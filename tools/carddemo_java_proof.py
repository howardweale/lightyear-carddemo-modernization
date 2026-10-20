"""Strict per-class mutation proof for the first idiomatic Java group."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET

CLASSES=('SignonService','SignonRules')
BASELINE='docs/modernization/carddemo-slice-1-evidence-2026-10-18/mutations.xml'


def summarize(nodes, classes):
    result={}
    for name in classes:
        selected=[n for n in nodes if (n.findtext('mutatedClass') or '').split('.')[-1].split('$')[0]==name]
        counts=Counter(n.attrib['status'] for n in selected);total=len(selected);killed=counts['KILLED']
        result[name]=dict(total=total,killed=killed,percent=100*killed/total if total else None,
                          status_counts=dict(counts),passed=bool(total and 10*killed>=9*total),
                          non_killed=[dict(status=n.attrib['status'],method=n.findtext('mutatedMethod'),
                                          line=n.findtext('lineNumber'),mutator=n.findtext('mutator'),
                                          description=n.findtext('description'))
                                      for n in selected if n.attrib['status']!='KILLED'])
    return result


def evaluate(path, root=Path('.')):
    path=Path(path);baseline=Path(root)/BASELINE
    old=summarize(ET.parse(baseline).getroot().findall('mutation'),('SignonService',))
    current=summarize(ET.parse(path).getroot().findall('mutation'),CLASSES) if path.exists() else summarize([],CLASSES)
    return dict(schema='carddemo-idiomatic-mutation/1',program='COSGN00C',
                passed=all(row['passed'] for row in current.values()),threshold=90,
                denominator='all generated mutants per required class; KILLED only',
                previous=dict(report=BASELINE,sha256=sha256(baseline.read_bytes()).hexdigest(),classes=old),
                current=current,remaining_statement_engine_programs=['COACTVWC','COACTUPC','COPAUS0C','COPAUS1C'])
