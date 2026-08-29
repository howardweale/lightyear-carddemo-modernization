# LIGHTYEAR customer estate assessment pilot

MS #31 turns the customer-specific typed estate from MS #30 into an evidence-first modernization
plan. It identifies connected application slices, retains missing boundaries, publishes explicit
development and live-evidence backlogs, and generates a content-addressed assessment plus v3
dossier. It never invents business priority, approves work, or dispatches the factory.

## Supported offline installation

The supported air-gapped path is the versioned source tree plus Python 3.11 or newer. It does not
run `pip`, contact a package index, or require a third-party runtime dependency:

```bash
tar -xf lightyear-carddemo-modernization-v0.31.0.tar
cd lightyear-carddemo-modernization-v0.31.0
./source-only-pilot.sh doctor
./source-only-pilot.sh verify
```

Windows PowerShell:

```powershell
Expand-Archive lightyear-carddemo-modernization-v0.31.0.zip
Set-Location lightyear-carddemo-modernization-v0.31.0
.\source-only-pilot.ps1 doctor
.\source-only-pilot.ps1 verify
```

Where standard Python build tooling is already available, `python -m pip install --no-deps .`
also exposes the optional `lightyear-pilot` console command. That convenience route is not required
for the air-gapped pilot.

The supported launchers are:

```bash
./source-only-pilot.sh doctor
./source-only-pilot.sh verify
./source-only-pilot.sh rehearse
```

## Customer source intake

The accepted pilot subset is UTF-8 text: COBOL, copybooks, PL/I and includes, JCL and procedures,
Db2 DDL/DCL/SQL, HLASM source and macros, IMS DBD/PSB definitions, VSAM IDCAMS control statements,
and approved JSON/YAML/XML/TXT configuration exports. A customer intake may use any applicable
subset; the committed release rehearsal deliberately covers all nine classes. Symbolic links, hidden
files, unsupported types, NUL/binary content, oversized inputs, and credential-shaped material fail
closed. The manifest keeps file paths, classifications, sizes, line counts, and hashes; it does not
copy source into the dossier.

```bash
./source-only-pilot.sh intake /approved/source pilot-authorization-123 work/pilot
./source-only-pilot.sh analyze /approved/source work/pilot
./source-only-pilot.sh assess work/pilot
./source-only-pilot.sh preflight work/pilot
./source-only-pilot.sh dossier work/pilot
```

The analysis stage writes `source-estate.snapshot.json.gz` and
`source-analysis.receipt.json`. The graph contains source paths, hashes, typed entities, and
relationships, but not source text. `unresolved_references` is an expected review queue, not a
reason to invent a relationship.

The assessment stage writes `estate-assessment.json` and `estate-assessment.md`. Its connected
components are candidate application slices, not automatic modernization units. Boundary closure
comes first; a business owner must then choose the pilot using criticality, value, ownership, and
change-window information that source code cannot supply.

## Reference release rehearsal

`verify` rebuilds the nine-class reference intake, customer graph, analysis receipt, JSON and
Markdown assessment, preflight, JSON dossier, and Markdown dossier in a new temporary directory. It validates all bindings and compares every byte with
`pilot/reference-output`. This is the clean-environment semantic identity control used by CI.

## Guides

- [Beginner quickstart](guides/beginner-quickstart.md)
- [Senior engineer and extension guide](guides/senior-engineer.md)
- [Security and operations guide](guides/security-operations.md)
- [Auditor verification guide](guides/auditor-verification.md)

## Truth boundary

The unlocked claim is:

> LIGHTYEAR can produce a governed, customer-specific static estate analysis, partition it into
> explainable connected application slices, and prepare an evidence-first modernization plan.

The dossier always keeps model qualification, live mainframe equivalence, and production readiness
false. Business priority is not inferred and factory dispatch remains disabled. Static source
relationships, custody, assessment, and development evidence cannot satisfy authorized original
execution or signed live equivalence.
