"""Lexical COBOL decision inventory with source spans; not path coverage."""
import re


def decisions(text, program, path):
    # Strip fixed-format comments and quoted literals before matching keywords.
    tokens, paragraph, scopes = [], None, {}
    for line_no, raw in enumerate(text.splitlines(), 1):
        fixed = len(raw) >= 7 and (raw[:6].isspace() or raw[:6].isdigit())
        if fixed and raw[6] in "*/":
            continue
        code = raw[7:72] if fixed else raw
        code = re.sub(r"'([^']|'')*'|\"([^\"]|\"\")*\"", " ", code.split("*>")[0]).upper()
        match = re.fullmatch(r"\s*([A-Z0-9][A-Z0-9-]*)\.\s*", code)
        if match and match[1] not in {"EXIT", "GOBACK", "CONTINUE", "END-IF", "END-EVALUATE", "END-PERFORM"}:
            paragraph = match[1]
        scopes[line_no] = paragraph
        tokens.extend((m[0], line_no) for m in re.finditer(r"[A-Z0-9][A-Z0-9-]*|\.", code))
    results = []
    for i, (word, start) in enumerate(tokens):
        kind, end = None, start
        if word in {"IF", "EVALUATE", "WHEN", "SEARCH"}:
            kind = word
        elif word == "PERFORM":
            for token, ln in tokens[i+1:i+40]:
                if token in {".", "END-PERFORM", "IF", "MOVE", "DISPLAY", "PERFORM"}:
                    break
                if token in {"UNTIL", "VARYING"}:
                    kind, end = "PERFORM " + token, ln
                    break
        elif word in {"AT", "INVALID"} and i+1 < len(tokens) and tokens[i+1][0] == {"AT": "END", "INVALID": "KEY"}[word]:
            kind, end = word + " " + tokens[i+1][0], tokens[i+1][1]
        if kind:
            results.append(dict(id=f"legacy:cobol-decision:{program}:{start}:{i}", program=program,
                                paragraph=scopes[start], path=path, line_start=start, line_end=end, construct=kind))
    return results


def coverage(rules, points, verdict):
    statuses = {r["id"]: r["status"] for r in verdict["rules"]}
    programs = {}
    for point in points:
        owners = sorted(r["id"] for r in rules if any(a["path"] == point["path"] and
            a["line_start"] <= point["line_end"] and a.get("line_end", a["line_start"]) >= point["line_start"]
            for a in r.get("derived_from", [])))
        programs.setdefault(point["program"], []).append({**point, "explained_by": owners})
    return dict(schema="lightyear-rule-coverage/1", programs={p: dict(decision_count=len(ps),
                explained_count=sum(bool(x["explained_by"]) for x in ps),
                explained_percentage=round(100*sum(bool(x["explained_by"]) for x in ps)/len(ps), 2),
                unexplained=[x for x in ps if not x["explained_by"]]) for p, ps in sorted(programs.items())},
                dead_rules=sorted(k for k,v in statuses.items() if v == "untested"),
                limitation="Lexical decision inventory and source-anchor overlap, not executed branch coverage.")
