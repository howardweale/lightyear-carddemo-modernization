"""Private source inventory with optional real parsers and conservative lexical hints.

The scanner NEVER establishes parse success, dependency closure or equivalence.
Only the hash-bound ScriptDom bridge or a non-opaque sqlglot AST can do syntax
admission. Native behavior is a separate gate. No database or network calls.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from lightyear_data.contracts import seal

MAX_SOURCE = 1024 * 1024
LEX = re.compile(
    r"(?P<space>\s+)|(?P<line>--[^\n]*)|(?P<block>/\*)|"
    r"(?P<string>N?'(?:''|[^'])*')|(?P<bracket>\[(?:\]\]|[^\]])*\])|"
    r'(?P<quoted>"(?:""|[^"])*")|(?P<word>[@#\w$]+)|(?P<symbol>.)', re.I | re.S
)
UNSUPPORTED = {
    "clr": r"\bEXTERNAL\s+NAME\b",
    "linked-server": r"\b(?:OPENQUERY|OPENROWSET|OPENDATASOURCE)\b",
    "extended-procedure": r"\bXP_\w+\b",
    "service-broker": r"\b(?:BEGIN\s+DIALOG|SEND\s+ON\s+CONVERSATION|RECEIVE|END\s+CONVERSATION)\b",
    "sql-agent": r"\bSP_(?:START|ADD|UPDATE|DELETE)_JOB\b",
    "filestream": r"\bFILESTREAM\b",
}
TRAPS = {
    1:r"\b(?:COLLATE|GROUP\s+BY|DISTINCT|JOIN|UNIQUE)\b",
    2:r"\b(?:CHAR|VARCHAR)\b", 3:r"\bLEN\s*\(",
    4:r"/|\b(?:INT|SMALLINT|BIGINT)\b", 5:r"\bISNULL\s*\(",
    6:r"\b(?:CAST|CONVERT)\b", 7:r"\bDATETIME\b",
    8:r"\bDATEDIFF\s*\(", 9:r"\b(?:DATEFIRST|DATEFORMAT|CONVERT)\b",
    10:r"\b(?:ROUND|MONEY|SMALLMONEY)\b", 11:r"\b(?:TRY|CATCH)\b",
    12:r"\b(?:XACT_ABORT|TRANCOUNT|TRANSACTION)\b|\bBEGIN\s+TRAN\b",
    13:r"\bRAISERROR\b", 14:r"\b(?:SCOPE_IDENTITY|@@IDENTITY|IDENTITY)\b",
    15:r"@@ROWCOUNT", 16:r"\bSELECT\b", 17:r"\b(?:OUTPUT|RETURN)\b",
    18:r"\bUPDATE\b", 19:r"\bMERGE\b", 20:r"#|\bTABLE\b",
    21:r"\b(?:SP_EXECUTESQL|EXEC|EXECUTE)\b", 22:r"\b(?:CURSOR|FETCH)\b",
    23:r"\b(?:TRIGGER|INSERTED|DELETED)\b", 24:r"\b(?:BIT|UNIQUEIDENTIFIER)\b",
    25:r"\bTOP\b",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def tokens(source: str) -> list[dict]:
    result, offset = [], 0
    while offset < len(source):
        m = LEX.match(source, offset)
        if not m:
            raise ValueError("unlexed-source")
        kind, end = m.lastgroup, m.end()
        if kind == "block":
            depth = 1
            while depth:
                nested = source.find("/*", end)
                close = source.find("*/", end)
                if close < 0:
                    raise ValueError("unterminated-comment")
                if nested >= 0 and nested < close:
                    depth += 1; end = nested + 2
                else:
                    depth -= 1; end = close + 2
        elif kind not in {"space", "line"}:
            value = m.group()
            if kind == "bracket": value = value[1:-1].replace("]]", "]")
            elif kind == "quoted": value = value[1:-1].replace('""', '"')
            if kind == "symbol" and value in {"'", '"', "["}:
                raise ValueError("unterminated-quoted-token")
            result.append({"kind":kind, "value":value, "start":offset, "end":end})
        offset = end
    return result


def scan(source: str) -> dict:
    ts = tokens(source)
    code = " ".join(t["value"] if t["kind"] != "string" else "STRING_LITERAL" for t in ts)
    # Identifiers and hints are private. No literal values are exported.
    unsupported = sorted(k for k,p in UNSUPPORTED.items() if re.search(p,code,re.I))
    heads = list(re.finditer(r"\b(?:CREATE\s+(?:OR\s+ALTER\s+)?|ALTER\s+)PROC(?:EDURE)?\s+([\w$]+)(?:\s*\.\s*([\w$]+))?",code,re.I))
    procedures = [".".join(m.groups()) if m.group(2) else "dbo."+m.group(1) for m in heads]
    dep = r"\b(FROM|JOIN|UPDATE|INTO|MERGE|EXEC|EXECUTE)\s+([\w#@]+(?:\s*\.\s*[\w#@]+){0,3})"
    reads, writes, calls = set(), set(), set()
    for m in re.finditer(dep,code,re.I):
        name = re.sub(r"\s", "", m.group(2))
        if name.startswith(("@","#")): continue
        verb = m.group(1).upper()
        (calls if verb in {"EXEC","EXECUTE"} else reads if verb in {"FROM","JOIN"} else writes).add(name)
    params = []
    if heads:
        tail = code[heads[0].end():]
        header = re.split(r"\bAS\b",tail,maxsplit=1,flags=re.I)[0]
        pattern = r"(@\w+)\s+([\w.]+)(\s*\([^)]*\))?([^,@]*)"
        for m in re.finditer(pattern, header, re.I):
            params.append({"name":m[1], "type":m[2]+(m[3] or ""),
                           "output":bool(re.search(r"\bOUT(?:PUT)?\b",m[4],re.I)),
                           "has_default":"=" in m[4]})
    control = {k:len(re.findall(p,code,re.I)) for k,p in {
        "if":r"\bIF\b", "while":r"\bWHILE\b", "try":r"\bBEGIN\s+TRY\b",
        "catch":r"\bBEGIN\s+CATCH\b", "cursor":r"\bCURSOR\b"}.items()}
    dynamic = bool(re.search(r"\bSP_EXECUTESQL\b|\bEXEC(?:UTE)?\s*\(|\bEXEC(?:UTE)?\s+@",code,re.I))
    transactions = re.findall(r"\b(?:BEGIN\s+TRAN(?:SACTION)?|COMMIT|ROLLBACK|SAVE\s+TRAN(?:SACTION)?|XACT_ABORT|@@TRANCOUNT)\b",code,re.I)
    nondeterministic = sorted(set(x.upper() for x in re.findall(
        r"\b(GETDATE|SYSDATETIME|GETUTCDATE|SYSUTCDATETIME|NEWID|RAND)\s*\(",code,re.I)))
    selects = list(re.finditer(r"\bSELECT\b(.*?)(?=;|\bGO\b|$)",code,re.I))
    shapes = [{"ordinal_hint":i+1,"projection":m[1].split("FROM")[0].strip(),
               "order_by_present":bool(re.search(r"\bORDER\s+BY\b",m[1],re.I)),
               "resolved":False} for i,m in enumerate(selects)]
    score = len(ts)//100 + sum(control.values())*2 + len(transactions)*3 + 8*dynamic + 5*bool(unsupported)
    return {"procedure_names":procedures,"parameters":params,
        "return_paths":len(re.findall(r"\bRETURN\b",code,re.I)),
        "result_set_shape_hints":shapes, "tables_read":sorted(reads), "tables_written":sorted(writes),
        "procedure_call_hints":sorted(calls), "dependencies":{"closure":"not-assessed",
            "functions_views_triggers_synonyms":"live catalog required","dynamic_sql_unresolved":dynamic},
        "control_flow":control,"transactions":transactions,"dynamic_sql":dynamic,
        "nondeterministic_calls":nondeterministic,"unsupported_features":unsupported,
        "trap_families":[n for n,p in TRAPS.items() if re.search(p,code,re.I)],
        "concurrency":"not-assessed","security_context":"not-assessed",
        "risk_score":score,"tier":"high" if score>=12 else "medium" if score>=4 else "low",
        "analysis_kind":"conservative-lexical-hints-not-dependency-proof"}


def parse(source: str, scriptdom: tuple[str,...] | None = None, *, allow_sqlglot=True) -> dict:
    raw = source.encode("utf-8")
    if len(raw)>MAX_SOURCE: raise ValueError("source-too-large")
    attempts = []
    if scriptdom:
        try:
            p = subprocess.run(list(scriptdom),input=source,text=True,encoding="utf-8",
                capture_output=True,timeout=30,check=False,shell=False)
            if len(p.stdout)>8*MAX_SOURCE: raise ValueError("parser-output-too-large")
            value = json.loads(p.stdout)
            if value.get("schema")!="tsql-scriptdom/1" or value.get("input_sha256")!=sha(raw):
                raise ValueError("parser-input-binding")
            if (p.returncode==0 and value.get("parsed") is True and value.get("errors")==[]
                and type(value.get("procedure_count")) is int and value["procedure_count"]>0
                and isinstance(value.get("version"),str) and value["version"]
                and isinstance(value.get("ast_nodes"),list) and value["ast_nodes"]):
                return {"status":"parsed","backend":"scriptdom","version":value["version"],
                        "ast":value,"attempts":attempts}
            attempts.append("scriptdom-rejected")
        except (OSError,subprocess.TimeoutExpired,ValueError,KeyError):
            attempts.append("scriptdom-unavailable-or-invalid")
    else:
        attempts.append("scriptdom-not-configured")
    if allow_sqlglot:
        try:
            import sqlglot
            from sqlglot import exp
            nodes = sqlglot.parse(source,read="tsql",error_level="RAISE")
            if not nodes or any(n is None or list(n.find_all(exp.Command)) for n in nodes):
                raise ValueError("opaque-parser-fallback")
            procedures = [n for node in nodes for n in node.find_all(exp.Create)
                          if str(n.args.get("kind","")).upper()=="PROCEDURE"]
            if not procedures: raise ValueError("no-procedure-ast")
            return {"status":"parsed","backend":"sqlglot","version":sqlglot.__version__,
                    "ast":{"procedure_count":len(procedures)},"attempts":attempts}
        except (ImportError,ValueError):
            attempts.append("sqlglot-unavailable-or-unsupported")
        except Exception:
            # Parser-specific exceptions may contain confidential source text.
            attempts.append("sqlglot-parse-error")
    return {"status":"unsupported","reason":"unparsed","backend":None,"attempts":attempts}


def _input(root: Path, name: str) -> Path:
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("missing-or-outside-pair-input")
    return path


def inventory(root: Path, pairs: list[dict], scriptdom=None, *, allow_sqlglot=True) -> dict:
    if not pairs: raise ValueError("empty-pair-inventory")
    seen, files, rows = set(), set(), []
    for pair in pairs:
        identity = pair["id"]
        if not isinstance(identity,str) or not identity or identity in seen: raise ValueError("duplicate-or-invalid-pair-id")
        seen.add(identity)
        try:paths = [_input(root,pair[k]) for k in ("source","twin")]
        except (KeyError,ValueError):
            rows.append(dict(id=identity,status='unsupported',reason='missing-or-outside-pair-input',
                source_sha256=None,twin_sha256=None,inventory={'tier':'high'},native_cases=0))
            continue
        if paths[0]==paths[1] or any(p in files for p in paths): raise ValueError("reused-pair-file")
        files.update(paths)
        raw, twin = (p.read_bytes() for p in paths)
        if len(raw)>MAX_SOURCE or len(twin)>MAX_SOURCE: raise ValueError("source-too-large")
        try:
            source=raw.decode("utf-8-sig"); hints=scan(source)
            parsed=parse(source,scriptdom,allow_sqlglot=allow_sqlglot)
        except (UnicodeError,ValueError):
            hints={"procedure_names":[],"tier":"high","unsupported_features":[]}
            parsed={"status":"unsupported","reason":"unparsed","attempts":["decoding-or-lexical-error"]}
        reason = "unparsed" if parsed["status"]!="parsed" else None
        if parsed["status"]=="parsed" and (len(hints["procedure_names"])!=1 or parsed["ast"]["procedure_count"]!=1):
            reason="requires-explicit-single-procedure-pairing"
        if hints["unsupported_features"]: reason="unsupported-feature"
        if any(d.get('cross_database') for d in parsed.get('ast',{}).get('semantic_catalogue',{}).get('dependencies',[])):
            reason='cross-database-dependency'
        rows.append({"id":identity,"source_sha256":sha(raw),"twin_sha256":sha(twin),
                     "syntax":parsed,"inventory":hints,"status":"unsupported" if reason else "inventoried",
                     "reason":reason,"twin_syntax":"not-assessed","native_cases":0})
    # Every delivered SQL file must be paired; nothing silently dropped.
    delivered={p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower()==".sql"}
    unpaired=sorted(sha(p.read_bytes()) for p in delivered-files)
    return seal({"schema":"tsql-procedure-inventory/1","pairs":rows,"pair_count":len(rows),
                 "inventory_complete":not unpaired,"unpaired_sql_sha256":unpaired,
                 "dependency_closure":False,"native_execution":False})


def public_summary(value: dict) -> dict:
    """Allowlist only: names, paths, literals, parser diagnostics never leave local inventory."""
    return seal({"schema":"tsql-procedure-inventory-summary/1","inventory_sha256":value["content_sha256"],
        "pair_count":value["pair_count"],
        "statuses":dict(Counter(r["status"] for r in value["pairs"])),
        "tiers":dict(Counter(r["inventory"]["tier"] for r in value["pairs"])),
        "bindings":[{"source_sha256":r["source_sha256"],"twin_sha256":r["twin_sha256"]} for r in value["pairs"]],
        "native_cases":0,"claim":"Source inventory only; no procedure equivalence assessed"})


def summary_markdown(value: dict) -> str:
    p=public_summary(value)
    return ("# Procedure intake summary\n\n"
            f"Pairs accounted for: {p['pair_count']}. Native cases: 0.\n\n"
            + "\n".join(f"- {k}: {v}" for k,v in sorted(p["statuses"].items()))
            + "\n\nRisk tiers: "+json.dumps(p["tiers"],sort_keys=True)
            + "\n\nDependency closure, target syntax, behavior and coverage remain unassessed.\n"
            + "\nInventory SHA-256: "+p["inventory_sha256"]+"\n")
