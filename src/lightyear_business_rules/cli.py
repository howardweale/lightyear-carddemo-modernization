"""Operator-only CLI integrated with lightyear-judge; no agent tool changes."""
import json
from pathlib import Path
from .engine import rules_from_mappings, issue, replay


def parsers(commands):
    for name in ("rule-check", "rule-replay", "rule-export", "rule-mode"):
        p = commands.add_parser(name)
        p.add_argument("--mapping", type=Path, action="append", required=True)
        p.add_argument("--records", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        if name == "rule-check":
            p.add_argument("--judge-key", type=Path, required=True)
            p.add_argument("--visibility", choices=("private", "public-development"), default="private")
        else:
            p.add_argument("--receipt", type=Path, required=True)
            p.add_argument("--public-key", type=Path, required=True)
        if name == "rule-mode":
            for name in ("proof", "tower-public-key"):
                p.add_argument("--" + name, type=Path, required=True)
            for name in ("rule-id", "tower-head", "tower-scope"):
                p.add_argument("--" + name, required=True)


def execute(args):
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    rules = rules_from_mappings([load(p) for p in args.mapping])
    records = load(args.records)
    if args.command == "rule-check":
        from lightyear_mainframe.zos_evidence import Signer
        result = issue(rules, records, Signer(args.judge_key), visibility=args.visibility)
    else:
        receipt, key = load(args.receipt), args.public_key.read_bytes()
        result = replay(receipt, rules, records, key)
        if args.command == "rule-mode":
            from .catalogue import disposition
            from .language import require
            matches = [r for r in rules if r["id"] == args.rule_id]
            require(len(matches) == 1, "unknown-rule")
            result = disposition(rules, matches[0], receipt, load(args.proof),
                                 args.tower_public_key.read_bytes(), args.tower_head, args.tower_scope)
        if args.command == "rule-export":
            from .catalogue import catalogue, html, dmn, scenarios
            result = catalogue(rules, receipt, key)
            args.output.mkdir(parents=True, exist_ok=False)
            (args.output / "catalogue.html").write_text(html(result), encoding="utf-8")
            (args.output / "rules.dmn").write_text(dmn(rules), encoding="utf-8")
            if receipt["visibility"] == "public-development":
                (args.output / "scenarios.feature").write_text(scenarios(rules, records, receipt, key), encoding="utf-8")
            args.output = args.output / "catalogue.json"
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    return dict(status="written", model_calls=0)
