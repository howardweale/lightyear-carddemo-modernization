# LIGHTYEAR source-only pilot

MS #29 packages the verified repository into a governed offline pilot. It accepts an explicitly
approved source directory, inventories only supported text classes, binds the current graph and
evidence receipts, publishes the exact prerequisites for live gates 6–8, and generates a
content-addressed JSON and Markdown dossier.

## Supported offline installation

The supported air-gapped path is the versioned source tree plus Python 3.11 or newer. It does not
run `pip`, contact a package index, or require a third-party runtime dependency:

```bash
tar -xf lightyear-carddemo-modernization-v0.29.0.tar
cd lightyear-carddemo-modernization-v0.29.0
./source-only-pilot.sh doctor
./source-only-pilot.sh verify
```

Windows PowerShell:

```powershell
Expand-Archive lightyear-carddemo-modernization-v0.29.0.zip
Set-Location lightyear-carddemo-modernization-v0.29.0
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
Db2 DDL/DCL/SQL, and approved JSON/YAML/XML/TXT configuration exports. A customer intake may use
any applicable subset; the committed release rehearsal deliberately covers all six classes. Symbolic links, hidden
files, unsupported types, NUL/binary content, oversized inputs, and credential-shaped material fail
closed. The manifest keeps file paths, classifications, sizes, line counts, and hashes; it does not
copy source into the dossier.

```bash
./source-only-pilot.sh intake /approved/source pilot-authorization-123 work/pilot
./source-only-pilot.sh preflight work/pilot
./source-only-pilot.sh dossier work/pilot
```

## Reference release rehearsal

`verify` rebuilds the six-class reference intake, preflight, JSON dossier, and Markdown dossier in
a new temporary directory. It validates all bindings and compares every byte with
`pilot/reference-output`. This is the clean-environment semantic identity control used by CI.

## Guides

- [Beginner quickstart](guides/beginner-quickstart.md)
- [Senior engineer and extension guide](guides/senior-engineer.md)
- [Security and operations guide](guides/security-operations.md)
- [Auditor verification guide](guides/auditor-verification.md)

## Truth boundary

The unlocked claim is:

> LIGHTYEAR is ready for a governed source-only pilot and subsequent authorized mainframe evidence
> collection.

The dossier always keeps model qualification, live mainframe equivalence, and production readiness
false. Source custody and development evidence cannot satisfy authorized original execution or
signed live equivalence.
