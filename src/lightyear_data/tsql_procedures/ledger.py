"""ASE provenance seeds are review obligations, never SQL Server qualification."""
import hashlib
import json
from pathlib import Path
from lightyear_data.contracts import canonical_bytes, content_hash, seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES

FAMILIES = {
1:("case-insensitive-collation","sort-order-collation","Declare SQL Server collation and PG normalization/collation; include uniqueness."),
2:("trailing-space-comparison","trailing-space-comparison","Compare SQL Server padding rules separately for equality, LIKE and binary collations."),
3:("len-trailing-spaces","trailing-space-comparison","LEN excludes trailing U+0020; preserve leading/internal spaces and NULL."),
4:("integer-division-and-precedence","money-expression-promotion","Check SQL Server integer division and precedence; do not promote integers implicitly."),
5:("isnull-first-type","select-assignment","First-argument type/length drives SQL Server ISNULL truncation; ASE is not authority."),
6:("empty-string-cast","empty-string-storage","SQL Server empty numeric/date conversion differs from both ASE storage and PG casts."),
7:("datetime-rounding","datetime-1-300-second","SQL Server datetime grid, range and displayed milliseconds require separate observations."),
8:("datediff-boundaries","datetime-range","SQL Server counts unit boundaries rather than whole elapsed units."),
9:("session-date-settings","timezone-absence","Bind DATEFIRST, DATEFORMAT and conversion styles; don't reuse ASE defaults."),
10:("round-and-money","money-rounding","Check signed ties, negative scales and money intermediate precision on SQL Server."),
11:("catch-side-effects","savepoint-rollback","SQL Server caught statement failure need not roll back prior work; PG EXCEPTION subtransaction does."),
12:("transaction-state","explicit-transaction","Bind XACT_ABORT and entry/exit @@TRANCOUNT; no wrapper rollback."),
13:("informational-raiserror","raiserror","Severity <=10 is informational; approved message/error mapping required."),
14:("identity-and-triggers","identity-gaps-on-rollback","SCOPE_IDENTITY differs from @@IDENTITY with triggers; sequences also advance on rollback."),
15:("rowcount-lifetime","rowcount-global","@@ROWCOUNT changes after intervening statements; capture DONE_IN_PROC separately."),
16:("multiple-result-sets","select-into","Explicit map between ordered TDS result sets and PG refcursors/OUT sets."),
17:("output-and-return","output-parameter","Capture OUTPUT values and default return 0 independently of result sets."),
18:("update-from-ambiguity","select-assignment","Several matching update sources leave the selected row unspecified; policy/repeated-run required."),
19:("merge","multirow-trigger","Qualify matched/unmatched effects and duplicate-source errors on exact engine versions."),
20:("temporary-object-scope","temp-table","Local procedure temp scope and table variables differ from persistent PG session temp tables."),
21:("dynamic-sql-binding","dynamic-exec","Inventory-only ASE unsupported status does not establish SQL Server support; preserve parameter binding."),
22:("cursor-fetch-status","rowcount-global","@@FETCH_STATUS is connection-scoped and can be changed by nested cursors."),
23:("set-based-triggers","inserted-deleted-tables","Multirow inserted/deleted facts must match statement semantics, not per-row assumptions."),
24:("bit-and-uuid","timestamp-row-version","SQL Server bit/uniqueidentifier are not ASE timestamp rowversions; explicit canonical types."),
25:("unordered-top","sort-order-collation","TOP without ORDER BY always requires a policy; a coincidental matching row is not equivalence."),
26:("null-and-collation-order","sort-order-collation","Preserve source ORDER BY; compare NULL position and declared collation order without sorting the evidence."),
}


def build_ledger(root: Path) -> dict:
    path=root/'data-modernization/sap-ase-source-adapter/compatibility-ledger.json'
    raw=path.read_bytes(); ase=json.loads(raw)
    if ase["content_sha256"]!=content_hash(ase): raise ValueError("ASE-ledger-hash")
    entries=[]
    for old in ase["entries"]:
        entries.append({"item_id":"sqlserver-review:"+old["item_id"],"scope":old["scope"],
            "source_semantics":{"dialect":"sqlserver-2022","status":"unverified"},
            "target_semantics":{"dialect":"postgresql-family","status":"unverified"},
            "classification":"policy-decision-required","rationale":"ASE seed only; applicability and SQL Server behavior not yet natively checked.",
            "evidence_required":["sqlserver-native-case","target-native-case","offline-replay"],
            "decision":None,"ase_item_id":old["item_id"],"ase_classification":old["classification"],
            "ase_entry_sha256":hashlib.sha256(canonical_bytes(old)).hexdigest(),
            "review_status":"pending-sqlserver-validation"})
    families=[]
    byid={e["item_id"] for e in ase["entries"]}
    for number,(name,seed,review) in FAMILIES.items():
        linked="ase-behavior:"+seed
        assert linked in byid
        families.append({"number":number,"trap_family":name,"ase_item_id":linked,
                         "required_sqlserver_check":review,"native_checked":False,
                         "classification":"policy-decision-required","decision":None})
    return seal({"schema":"tsql-compatibility-ledger/1","ase_ledger_file_sha256":hashlib.sha256(raw).hexdigest(),
        "ase_ledger_content_sha256":ase["content_sha256"],"entries":entries,"trap_families":families,
        "classifications":list(COMPATIBILITY_CLASSES),"inherited_decisions_applied":False,
        "sqlserver_native_qualification":False,"normalization_rules":[]})


def validate_ledger(root, value):
    if value!=build_ledger(root): raise ValueError("ledger-drift-or-unverified-promotion")
    return True
