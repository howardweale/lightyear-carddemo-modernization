"""Render a new dated packet from verified release records; never rewrite history."""
import argparse
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release_status_records import ROOT, PHASE2_PUBLIC_ROOT, load, render


def build(commit=None, root=ROOT):
    model = load(root)
    value, _ = render(model)
    import json
    date=value['as_of']+'-handoff-refresh'
    lines = ['# Howard decision packet — '+date, '',
             'Decisions only. The measured status and failure inventories are in the current status and program verdicts.', '',
             '| Order | Decision | Consequence of signing |', '| --- | --- | --- |']
    index=root/'docs/factory/intcalc-signing-order-2026-10-16.json'
    consequences=['Accept only the pinned twin loader-domain exclusion; no kill credit.',
        'Accept the exact APPL-RESULT class arguments, twin-scoped.',
        'Accept the 30 individual and two compiler-proven items within twin scope.',
        'Approve threshold/3 policy subject to its four typed conditions; not effective yet.',
        'Accept the exact line 189 false-edge argument.',
        'Make the policy effective only after all typed evidence is present. Currently refuses; signatures cannot establish non-provisional evidence.']
    if index.exists():
        for row,reason in zip(json.loads(index.read_bytes())['items'],consequences):
            lines.append(f"| {row['order']} | [{Path(row['path']).stem}]({Path(row['path']).name}) | {reason} |")
    else: lines.append('| Pending | INTCALC ordered packet | Missing request inventory; nothing to sign. |')
    lines+=['| Separate | [POSTTRAN line 203](posttran-io-exception-request-2026-10-16.json) | Accept only the pinned structurally unreachable false edge. Nine campaign gaps remain. |',
            '| Separate | [z/OS loader-domain proposal](intcalc-zos-loader-domain-proposal-2026-10-16.json) | Requires real loader capture and confirmation before any z/OS-facing overlay. |',
            '| Separate | [POSTTRAN execution request]('+PHASE2_PUBLIC_ROOT+'posttran-phase2-authorization-request-2026-10-16.json) | One candidate/twin comparison, only after signed proof and exact variables; not release authority. |']
    if model.get('phase2'):
        p=value['phase2']
        lines+=['', '| Phase 2 | Plan seal | Executable commit | Signing deadline (UTC) | Days remaining |', '|---|---|---|---|---:|',
                f"| POSTTRAN | `{p['plan_sha256']}` | `{p['executable_commit']}` | {p['signing_deadline']} | {p['days_remaining']} |",
                'Evaluated at '+p['evaluated_at']+'. '+('WARNING: five days or fewer remain.' if p['warning'] else 'More than five days remain.'),
                'Compiler expiry: '+p['artifact_expires_at']+'. No signing or execution has been performed.']
    lines += ['', 'Current public retention: '+', '.join('['+Path(p).name+']('+Path(p).name+')' for p in model.get('retention',[]))+'. Historical packets remain unchanged.']
    lines += ['', 'All new requests are unsigned. Exact-final-green-commit merge approval remains separate.', '']
    path = root/'docs/factory'/('howard-decision-packet-'+date+'.md')
    path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit')  # Compatibility; measured head comes only from receipts.
    args = parser.parse_args()
    build(args.source_commit)
