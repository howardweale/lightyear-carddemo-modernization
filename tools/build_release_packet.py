"""Render a new dated packet from verified release records; never rewrite history."""
import argparse
from tools.release_status_records import ROOT, load, render


def build(commit=None, root=ROOT):
    model = load(root)
    value, status = render(model)
    release = model['release']
    lines = ['# Howard decision packet — '+release['prepared_on'], '',
             status.split('\n', 2)[2],
             '## Decisions and blockers', '', *['- '+s for s in release['blockers']], '',
             '## Targeted comparisons', '', '| Program | Mutant | Valid comparisons / cases |', '| --- | --- | --- |']
    for program, record in release['programs'].items():
        for row in record['targets']:
            lines.append(f"| {program} | {row['id']} | {row['targeted_valid_comparisons']}/{row['targeted_cases']} |")
    lines += ['', 'No request in this packet is signed or effective. POSTTRAN execution requires its separate exact plan and signed authorization. See the newest POSTTRAN authorization record for readiness.', '']
    path = root/'docs/factory'/('howard-decision-packet-'+release['prepared_on']+'.md')
    path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit')  # Compatibility; measured head comes only from receipts.
    args = parser.parse_args()
    build(args.source_commit)
