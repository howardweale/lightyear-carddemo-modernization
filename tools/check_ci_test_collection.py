"""Static CI collection inventory; never import or execute the test modules."""
import argparse
import fnmatch
import json
from pathlib import Path
import re
import yaml


def commands(text,root):
    yield from text.splitlines()
    # Follow only literal repository scripts invoked by a run step. Merely
    # naming a test in a comment or a workflow path filter is not collection.
    for match in re.finditer(r'(?:^|\s)(?:\./|\.\\)([\w.-]+\.(?:sh|ps1))(?=\s|$)',text):
        path=root/match[1]
        if path.is_file():yield from path.read_text(encoding='utf-8').splitlines()


def inventory(root):
    root=Path(root);tests={p.name for p in (root/'tests').glob('test_*.py')}
    covered={name:[] for name in tests}
    for path in sorted((root/'.github/workflows').glob('*.yml')):
        workflow=yaml.load(path.read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
        for job in workflow.get('jobs',{}).values():
            if str(job.get('if','')).strip() in ('false','${{ false }}'):continue
            for step in job.get('steps',[]):
                if str(step.get('if','')).strip() in ('false','${{ false }}'):continue
                for line in commands(step.get('run',''),root):
                    line=line.strip()
                    if line.startswith(('#','echo ','printf ','Write-Output ')) or '-m unittest' not in line:continue
                    arguments=line.split('-m unittest',1)[1]
                    if 'discover' in arguments:
                        # The repository's Bash and PowerShell wrappers use
                        # project_dir/tests and Join-Path $ProjectDir "tests".
                        if 'tests' not in arguments:continue
                        match=re.search(r'(?:-p|--pattern)(?:=|\s+)([\"\']?)([^\s\"\']+)\1',arguments)
                        patterns=[match[2] if match else 'test*.py']
                    else:
                        patterns=[m+'.py' for m in re.findall(r'(?<![\w/])(test_\w+)(?=\s|$)',arguments)]
                    for name in tests:
                        if any(fnmatch.fnmatchcase(name,p) for p in patterns):
                            covered[name].append(path.as_posix())
    return {name:sorted(set(paths)) for name,paths in sorted(covered.items())}


def check(root):
    rows=inventory(root);missing=[name for name,paths in rows.items() if not paths]
    if missing:raise ValueError('CI-test-not-collected:'+','.join(missing))
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.')
    args=p.parse_args();print(json.dumps(check(args.root),indent=2))
