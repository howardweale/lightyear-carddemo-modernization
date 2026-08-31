# LIGHTYEAR governed pilot selection and work packaging

MS #32 turns the advisory application slices from MS #31 into one human-selected, evidence-bound
development work package. It records business outcomes and success criteria, preserves every
missing boundary, and creates graph-scoped technology cells. It never signs or admits a factory
work order, dispatches an agent, authorizes native execution, or promotes production readiness.

## Supported offline installation

The supported air-gapped path is the versioned source tree plus Python 3.11 or newer. It does not
run `pip`, contact a package index, or require a third-party runtime dependency:

```bash
tar -xf lightyear-carddemo-modernization-v0.33.0.tar
cd lightyear-carddemo-modernization-v0.33.0
./source-only-pilot.sh doctor
./source-only-pilot.sh verify
```

Windows PowerShell:

```powershell
Expand-Archive lightyear-carddemo-modernization-v0.33.0.zip
Set-Location lightyear-carddemo-modernization-v0.33.0
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
./source-only-pilot.sh select work/pilot /approved/pilot-selection.request.json
./source-only-pilot.sh package work/pilot
```

The analysis stage writes `source-estate.snapshot.json.gz` and
`source-analysis.receipt.json`. The graph contains source paths, hashes, typed entities, and
relationships, but not source text. `unresolved_references` is an expected review queue, not a
reason to invent a relationship.

The assessment stage writes `estate-assessment.json` and `estate-assessment.md`. Its connected
components are candidate application slices, not automatic modernization units. Boundary closure
comes first; a business owner must then choose the pilot using criticality, value, ownership, and
change-window information that source code cannot supply.

## Governed selection and work package

`select` binds one human decision to the exact assessment and dossier. The request must identify the
business and technical owners, record why the slice was chosen, define outcomes and success
criteria, prohibit raw customer data in the source-only flow, and disposition every unresolved
reference. A deferred boundary keeps the selection blocked.

`package` creates one draft development cell per selected technology. Each cell has exact source
paths, graph nodes, coordination dependencies, a bounded output root, expected deliverables,
acceptance evidence, and live evidence. The reference package contains five cells: COBOL, PL/I,
JCL, Db2, and HLASM.

`work_package_ready: true` means the inputs are complete enough to author detailed signed work
orders. It does not mean any work order is admitted or that factory dispatch is allowed.

## Integrated pilot qualification

MS #42 binds the reference package's exact COBOL, PL/I, JCL, Db2, and HLASM cells into one bounded
development qualification. It verifies the selected source paths and graph relationships, the five
cell dependencies, online and batch paths, shared database behavior, copybook and schema contracts,
job flow, assembler branching, and cross-language calls.

```bash
./integrated-pilot-qualification.sh build
./integrated-pilot-qualification.sh verify
```

The resulting conformance receipt, cell evidence matrix, compatibility ledger, and twelve-gate
qualification live in `pilot/integrated-qualification`. `wave_2_integrated_development_ready: true`
means the deterministic selected-slice reference evidence passes. It does not admit or dispatch a
factory work order. Every live evidence item remains blocked, and native runtime, mainframe
equivalence, production release, and production readiness remain false.

## Reference release rehearsal

`verify` rebuilds the nine-class reference intake, customer graph, analysis receipt, JSON and
Markdown assessment, preflight, dossier, selection, and JSON/Markdown work package in a new temporary directory. It validates all bindings and compares every byte with
`pilot/reference-output`. This is the clean-environment semantic identity control used by CI.

## Guides

- [Beginner quickstart](guides/beginner-quickstart.md)
- [Senior engineer and extension guide](guides/senior-engineer.md)
- [Security and operations guide](guides/security-operations.md)
- [Auditor verification guide](guides/auditor-verification.md)

## Truth boundary

The unlocked claim is:

> LIGHTYEAR can turn one recorded human pilot selection into a deterministic, graph-scoped,
> multi-technology development work package.

The approval record is attributable and content-bound but remains external evidence; the source-only
flow does not cryptographically verify the human identity. All generated cells remain draft scopes.
Model qualification, factory dispatch, live mainframe equivalence, and production readiness remain
false or blocked.
