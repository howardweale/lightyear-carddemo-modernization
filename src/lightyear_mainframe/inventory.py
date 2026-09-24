"""Versioned source-level decision denominator and unobserved coverage baseline."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess

from .source import Corpus, SourceError, sha

PROFILE = 'cobol-source-outcomes-v1'
# Tokens starting an imperative statement terminate a condition/header. These
# are COBOL verbs, never substrings of identifiers or contents of literals.
VERBS = set('ACCEPT ADD ALLOCATE ALTER CALL CANCEL CLOSE COMPUTE CONTINUE DELETE DISPLAY DIVIDE ENTRY EVALUATE EXEC EXIT FREE GENERATE GO GOBACK IF INITIALIZE INITIATE INSPECT INVOKE JSON MERGE MOVE MULTIPLY OPEN PERFORM READ RELEASE RETURN REWRITE SEARCH SET SORT START STOP STRING SUBTRACT SUPPRESS TERMINATE UNSTRING WRITE XML'.split())
BOUNDARY = VERBS | set('ELSE WHEN AT INVALID NOT END-IF END-EVALUATE END-PERFORM END-SEARCH END-READ END-WRITE END-REWRITE END-START END-CALL END-COMPUTE END-STRING END-UNSTRING .'.split())
HANDLERS = {
    ('AT', 'END'): {'READ', 'RETURN'},
    ('INVALID', 'KEY'): {'READ', 'WRITE', 'REWRITE', 'DELETE', 'START'},
    ('ON', 'SIZE', 'ERROR'): {'ADD', 'SUBTRACT', 'MULTIPLY', 'DIVIDE', 'COMPUTE'},
    ('ON', 'EXCEPTION'): {'CALL', 'ACCEPT', 'DISPLAY', 'XML', 'JSON'},
    ('ON', 'OVERFLOW'): {'STRING', 'UNSTRING'},
}


def scan(tokens, program):
    decisions, issues, boundaries = [], [], []
    values = [t.text for t in tokens]
    start = next((i+2 for i in range(len(values)-1)
                  if values[i:i+2] == ['PROCEDURE', 'DIVISION']), None)
    if start is None:
        return [], [dict(cause='missing-procedure-division', program=program)], []
    # Determine every possible destination of a statically named ALTER site.
    alters = {}
    in_exec = False
    for i in range(start, len(tokens)):
        if values[i] == 'EXEC': in_exec = True
        if values[i] == 'END-EXEC': in_exec = False
        if in_exec: continue
        if values[i] == 'ALTER':
            end = next((j for j in range(i+1, len(tokens)) if values[j] in VERBS or values[j] == '.'), len(tokens))
            part = values[i+1:end]
            if len(part) == 5 and part[1:4] == ['TO', 'PROCEED', 'TO']:
                alters.setdefault(part[0], set()).add(part[4])
            else:
                issues.append(dict(cause='unsupported-alter', **tokens[i].location()))
    scopes, owners = [], []
    handler_decisions = {}
    paragraph = None

    def header(i, stops=VERBS | {'WHEN', 'ELSE', '.'}):
        j = i+1
        while j < len(tokens) and values[j] not in stops and not values[j].startswith('END-'):
            j += 1
        return ' '.join(values[i:j]), j

    def add(i, kind, labels):
        t = tokens[i]
        identity = json.dumps([PROFILE, program, t.location(), kind], sort_keys=True)
        decision_id = 'decision:' + sha(identity.encode())[:24]
        result = dict(id=decision_id, program=program, kind=kind, **t.location(),
                      text=header(i)[0], outcomes=[])
        for label in labels:
            result['outcomes'].append(dict(id=f'{decision_id}/{label}', label=label))
        decisions.append(result)
        return result

    def finish(scope):
        kind, entry = scope
        if kind == 'EVALUATE':
            if not entry['outcomes']:
                issues.append(dict(cause='evaluate-without-when', decision=entry['id']))
            if not any(o['label'] == 'other' for o in entry['outcomes']):
                entry['outcomes'].append(dict(id=entry['id']+'/no-match', label='no-match', implicit=True))
        elif kind == 'SEARCH':
            entry['outcomes'].append(dict(id=entry['id']+'/exhausted', label='exhausted'))

    i = start
    while i < len(tokens):
        word, token = values[i], tokens[i]
        if word == 'EXEC':
            end = next((j for j in range(i+1, len(tokens)) if values[j] == 'END-EXEC'), None)
            if end is None:
                issues.append(dict(cause='unterminated-exec', **token.location())); break
            boundaries.append(dict(kind='embedded-' + values[i+1].lower(), **token.location(),
                                   text=' '.join(values[i:end+1])))
            i = end+1; continue
        if word == '.':
            while scopes:
                finish(scopes.pop())
            owners.clear()
        if token.column <= 11 and word not in VERBS and i+1 < len(values) and values[i+1] == '.':
            paragraph = word
        if word in VERBS:
            owners.append((word, i))
        if word.startswith('END-'):
            opcode = word[4:]
            owner_idx = next((j for j in range(len(owners)-1, -1, -1) if owners[j][0] == opcode), None)
            if owner_idx is not None:
                del owners[owner_idx:]
        if word == 'IF':
            add(i, 'if', ['true', 'false'])
        elif word in ('EVALUATE', 'SEARCH'):
            scopes.append((word, add(i, word.lower(), [])))
        elif word in ('END-EVALUATE', 'END-SEARCH'):
            if not scopes or scopes[-1][0] != word[4:]:
                issues.append(dict(cause='unbalanced-selection', **token.location()))
            else:
                finish(scopes.pop())
        elif word == 'WHEN':
            if not scopes:
                issues.append(dict(cause='orphan-when', **token.location()))
            else:
                entry = scopes[-1][1]
                label = 'other' if values[i+1:i+2] == ['OTHER'] else f'when-{len(entry["outcomes"])+1}'
                entry['outcomes'].append(dict(id=entry['id']+'/'+label, label=label,
                                             text=header(i, VERBS | {'WHEN', '.'})[0], **token.location()))
        elif word == 'PERFORM':
            _, end = header(i)
            part = values[i+1:end]
            for j in range(i+1, end):
                if values[j] == 'UNTIL':
                    if values[j+1:j+2] == ['EXIT']:
                        boundaries.append(dict(kind='unconditional-loop', **token.location()))
                    else:
                        entry = add(j, 'perform-until', ['continue', 'exit'])
                        entry['test_position'] = 'after' if ['TEST', 'AFTER'] == part[:2] or 'AFTER' in part[:4] else 'before'
            if 'TIMES' in part:
                add(i, 'perform-times', ['repeat', 'done'])
            if 'VARYING' in part and 'UNTIL' not in part:
                issues.append(dict(cause='unresolved-perform-varying', **token.location()))
        elif word == 'GO':
            _, end = header(i)
            part = values[i+1:end]
            if part[:1] == ['TO']:
                part = part[1:]
            if 'DEPENDING' in part:
                destinations = part[:part.index('DEPENDING')]
                add(i, 'go-depending', [f'target-{n+1}:{p}' for n, p in enumerate(destinations)] + ['out-of-range'])
            elif paragraph in alters:
                add(i, 'altered-go', ['target:'+p for p in sorted(alters[paragraph] | set(part))])
        elif word == 'CALL':
            boundaries.append(dict(kind='external-call', **token.location(), text=header(i)[0]))
        # Explicit exception alternatives belong to one decision per operation,
        # even if both the positive and NOT phrase are present.
        for phrase, opcodes in HANDLERS.items():
            full = tuple(values[i:i+len(phrase)]) == phrase
            abbreviated = (phrase[0] in ('AT', 'ON') and
                           tuple(values[i:i+len(phrase)-1]) == phrase[1:] and
                           values[i-1:i] != [phrase[0]])
            if not full and not abbreviated:
                continue
            eligible = opcodes | ({'SEARCH'} if phrase == ('AT', 'END') else set())
            owner = next((o for o in reversed(owners) if o[0] in eligible), None)
            if owner and owner[0] == 'SEARCH': continue
            if owner is None:
                issues.append(dict(cause='unbound-condition-handler', **token.location())); continue
            key = (owner[1], phrase)
            if key not in handler_decisions:
                entry = add(owner[1], '-'.join(phrase).lower(), ['condition', 'normal'])
                handler_decisions[key] = entry
            entry = handler_decisions[key]
            entry.setdefault('handlers', []).append(dict(negative=values[i-1:i] == ['NOT'], **token.location()))
        i += 1
    while scopes:
        finish(scopes.pop())
        issues.append(dict(cause='unterminated-selection', program=program))
    return decisions, issues, boundaries


def inventory(root: Path):
    corpus = Corpus(root)
    programs, decisions, issues, boundaries = [], [], [], []
    for path in corpus.files:
        if path.suffix.lower() not in ('.cbl', '.cob'):
            continue
        relative = path.relative_to(corpus.root).as_posix()
        try:
            tokens = corpus.expand(path)
            found, problems, opaque = scan(tokens, relative)
        except (SourceError, UnicodeError) as exc:
            found, opaque = [], []
            problems = [dict(cause='source-not-inventoried', program=relative, detail=str(exc))]
        decisions.extend(found); issues.extend(problems); boundaries.extend(opaque)
        programs.append(dict(path=relative, sha256=corpus.hashes[relative], decisions=len(found),
                             outcomes=sum(len(d['outcomes']) for d in found), issues=len(problems)))
    issues.extend(corpus.issues)
    try:
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True))
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, dirty = None, None
    result = dict(schema_version='1.0', profile=PROFILE,
                  generator={name: sha(Path(__file__).with_name(name).read_bytes())
                             for name in ('inventory.py', 'source.py')},
                  source=dict(commit=commit, working_tree_dirty=dirty, files=corpus.hashes),
                  programs=programs, decisions=decisions, copy_references=corpus.references,
                  issues=issues, boundaries=boundaries,
                  summary=dict(programs=len(programs), decisions=len(decisions),
                               outcomes=sum(len(d['outcomes']) for d in decisions),
                               by_kind=dict(sorted(Counter(d['kind'] for d in decisions).items())),
                               issues_by_cause=dict(sorted(Counter(i['cause'] for i in issues).items()))),
                  claims=dict(static_source_inventory=True, compiled_branch_complete=False,
                              runtime_coverage=None, mainframe_equivalent=False),
                  limitations=[
                      'Fixed format uses columns 7-72 and eight-column tab stops; positions use expanded columns. Compiler source-format settings still require reconciliation.',
                      'Source outcomes include syntactic alternatives; reachability and compiler-generated branches are not proved.',
                      'Each EVALUATE WHEN is a selection alternative, including alternatives sharing a body; missing OTHER adds no-match.',
                      'SEARCH counts declared WHEN selections and exhaustion, not internal binary-search comparisons.',
                      'COPY expansions are per inclusion; unresolved compiler libraries and embedded CICS/SQL/IMS behavior are listed.',
                      'Compound conditions are one decision: this is not MC/DC or path coverage.',
                      'The denominator must be reconciled with compiler listings, options and deployed load modules before a z/OS coverage claim.',
                  ])
    result['inventory_sha256'] = sha(json.dumps(result, sort_keys=True, separators=(',', ':')).encode())
    return result


def coverage(inventory, receipt=None):
    """Bind declared observations to exact inventory IDs; never attest z/OS here."""
    expected = sha(json.dumps({k: v for k, v in inventory.items() if k != 'inventory_sha256'},
                              sort_keys=True, separators=(',', ':')).encode())
    if inventory.get('profile') != PROFILE or inventory.get('inventory_sha256') != expected:
        raise ValueError('inventory content hash or profile mismatch')
    ids = [o['id'] for d in inventory['decisions'] for o in d['outcomes']]
    denominator = len(ids)
    if len(set(ids)) != denominator or inventory['summary']['outcomes'] != denominator:
        raise ValueError('inconsistent inventory outcome denominator')
    result = dict(inventory_sha256=inventory['inventory_sha256'], denominator=denominator,
                  observed_outcomes=None, coverage_percent=None, evidence_class='unobserved',
                  native_coverage_percent=None, mainframe_equivalent=False)
    if receipt is None:
        return result
    if receipt.get('inventory_sha256') != inventory['inventory_sha256']:
        raise ValueError('coverage inventory hash mismatch')
    if receipt.get('evidence_class') not in ('simulated', 'local_observed'):
        raise ValueError('native evidence needs compiler/load-module reconciliation; this importer cannot attest z/OS')
    known = {o['id'] for d in inventory['decisions'] for o in d['outcomes']}
    hits = receipt.get('outcome_ids')
    if not isinstance(hits, list) or any(not isinstance(x, str) or x not in known for x in hits):
        raise ValueError('unknown outcome IDs')
    result.update(observed_outcomes=len(set(hits)), coverage_percent=100*len(set(hits))/denominator if denominator else None,
                  evidence_class=receipt['evidence_class'])
    return result


def markdown(report):
    s = report['summary']
    lines = ['# CardDemo COBOL decision inventory', '',
             f"Source revision: `{report['source']['commit']}`.", '',
             f"Inventoried **{s['programs']:,} programs**, **{s['decisions']:,} source decisions** and **{s['outcomes']:,} source outcome slots** under `{PROFILE}`.", '',
             'This is a source-level test-planning denominator. Runtime coverage is **unobserved**, and compiled branch completeness is **not claimed**.', '',
             '| Decision kind | Decisions |', '| --- | ---: |']
    lines += [f'| {kind} | {count:,} |' for kind, count in s['by_kind'].items()]
    lines += ['', '## Scope and open boundaries', ''] + ['- '+x for x in report['limitations']]
    lines += ['', '| Issue | Count |', '| --- | ---: |'] + [f'| {k} | {v} |' for k, v in s['issues_by_cause'].items()]
    lines += ['', '## Per-program denominator', '', '| Program | Decisions | Outcomes |', '| --- | ---: | ---: |']
    lines += [f"| {p['path']} | {p['decisions']} | {p['outcomes']} |" for p in report['programs']]
    lines += ['', f"Inventory SHA-256: `{report['inventory_sha256']}`", '',
              'The JSON inventory contains every outcome ID, physical source location, COPY inclusion chain, source hash, issue and external boundary. No runtime hits have been inferred from this inventory.', '']
    return '\n'.join(lines)
