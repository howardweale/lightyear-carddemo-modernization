"""Report recently merged non-main PR commits that are not reachable from main."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

MARKER = '<!-- lightyear-stranded-work-audit/1 -->'


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def oid(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('stranded-work-commit')
    return value


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('stranded-work-repository')
        self.prefix = 'repos/' + repository + '/'

    def request(self, route, method='GET', data=None):
        command = ['gh', 'api', self.prefix + route, '--method', method]
        if data is not None: command += ['--input', '-']
        route_label = route.split('?', 1)[0]
        if len(route_label) > 200 or not re.fullmatch(r'[A-Za-z0-9_./-]+', route_label):
            route_label = 'redacted'
        read_only = method == 'GET' and data is None
        attempts = 3 if read_only else 1
        for attempt in range(1, attempts + 1):
            try:
                result = subprocess.run(command, input=None if data is None else json.dumps(data),
                    text=True, capture_output=True, check=False, timeout=60)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f'stranded-work-api-timeout: {method} {route_label}') from None
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    raise RuntimeError(f'stranded-work-api-json: {method} {route_label}') from None
            statuses = set(re.findall(r'\bHTTP ([1-5][0-9]{2})\b', result.stderr or ''))
            status = next(iter(statuses)) if len(statuses) == 1 else 'unknown'
            if status in {'500', '502', '503', '504'} and attempt < attempts:
                time.sleep(2 ** attempt)
                continue
            # Never print captured bodies, headers, credentials or issue payloads.
            raise RuntimeError(f'stranded-work-api: {method} {route_label} '
                f'HTTP {status}; exit {result.returncode}; attempts {attempt}')

    def pages(self, route):
        result = []
        for page in range(1, 1001):
            batch = self.request(route + ('&' if '?' in route else '?') + f'per_page=100&page={page}')
            if not isinstance(batch, list): raise ValueError('stranded-work-page')
            result.extend(batch)
            if len(batch) < 100: return result
        raise ValueError('stranded-work-pagination')


def audit(client, now):
    now = now.astimezone(timezone.utc); cutoff = now - timedelta(days=14)
    main = oid(client.request('git/ref/heads/main')['object']['sha'])
    candidates = []; seen = set()
    for pr in client.pages('pulls?state=closed&sort=updated&direction=desc'):
        number = pr['number']
        if number in seen: raise ValueError('stranded-work-duplicate-pr')
        seen.add(number)
        if not pr.get('merged_at') or pr['base']['ref'] == 'main': continue
        merged = timestamp(pr['merged_at'])
        if cutoff <= merged <= now: candidates.append(pr)
    cache = {}; rows = []
    for pr in sorted(candidates, key=lambda p: p['number']):
        commits = client.pages(f'pulls/{pr["number"]}/commits')
        detail = client.request(f'pulls/{pr["number"]}')
        count = detail['commits']
        if type(count) is not int or count < 1 or len(commits) != count:
            raise ValueError('stranded-work-incomplete-commits')
        if detail['head']['sha'] != pr['head']['sha'] or detail['base']['ref'] != pr['base']['ref']:
            raise ValueError('stranded-work-pr-moved')
        hashes = [oid(c['sha']) for c in commits]
        if len(hashes) != len(set(hashes)): raise ValueError('stranded-work-duplicate-commit')
        missing = []
        for commit in hashes:
            if commit not in cache:
                comparison = client.request(f'compare/{main}...{commit}')
                status = comparison['status']; ahead = comparison['ahead_by']
                if status not in ('identical', 'behind', 'ahead', 'diverged') or type(ahead) is not int or ahead < 0:
                    raise ValueError('stranded-work-comparison')
                reachable = status in ('identical', 'behind')
                if reachable != (ahead == 0): raise ValueError('stranded-work-inconsistent-comparison')
                cache[commit] = reachable
            if not cache[commit]: missing.append(commit)
        if missing:
            rows.append(dict(pr=pr['number'], url=pr['html_url'], base=pr['base']['ref'],
                merged_at=pr['merged_at'], head=oid(pr['head']['sha']),
                merge_commit=oid(pr['merge_commit_sha']), unreachable_commits=missing))
    if client.request('git/ref/heads/main')['object']['sha'] != main:
        raise ValueError('stranded-work-main-moved')
    return dict(schema='stranded-work-audit/1', evaluated_at=now.isoformat(),
        since=cutoff.isoformat(), main=main, scanned_merged_non_main=len(candidates),
        compared_commits=len(cache), stranded=rows, complete=True)


def markdown(report):
    lines = [MARKER, '# Merged work not reachable from main', '',
        f"As of {report['evaluated_at']}; main `{report['main']}`; window starts {report['since']}.", '',
        f"{len(report['stranded'])} stranded PRs among {report['scanned_merged_non_main']} recent non-main merges.", '']
    for row in report['stranded']:
        lines += [f"- [PR #{row['pr']}]({row['url']}) into `{row['base']}`; merged {row['merged_at']}; unreachable commits:"]
        lines += ['  - `' + commit + '`' for commit in row['unreachable_commits']]
    if not report['stranded']: lines.append('None. All inspected PR commits are reachable from the pinned main snapshot.')
    lines += ['', 'Reachability is not a claim of CI success or behavioral equivalence. No merge is performed by this audit.']
    return '\n'.join(lines) + '\n'


def update_issue(client, report):
    matches = [issue for issue in client.pages('issues?state=all')
               if 'pull_request' not in issue and MARKER in (issue.get('body') or '')]
    if len(matches) > 1: raise ValueError('stranded-work-ambiguous-issue')
    body = markdown(report); state = 'open' if report['stranded'] else 'closed'
    if not matches and state == 'closed': return None
    if matches and matches[0]['body'] == body and matches[0]['state'] == state: return matches[0]
    payload = dict(title='Merged work not reachable from main', body=body)
    if matches:
        payload['state'] = state
        return client.request(f'issues/{matches[0]["number"]}', 'PATCH', payload)
    return client.request('issues', 'POST', payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--issue', action='store_true')
    args = parser.parse_args(argv)
    if args.issue and os.environ.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch'):
        raise ValueError('stranded-work-issue-event')
    client = GitHub(args.repository)
    report = audit(client, datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    body = markdown(report)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream: stream.write(body)
    if args.issue: update_issue(client, report)
    print(body)
    # Existing backlog is a report, not a deadlock that prevents its own landing PRs.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
