# Architecture

As of 2026-11-16, this is the target layering and a map of existing packages.
The boundaries are not yet fully enforced: the judge still imports higher-layer
code, trust primitives live in Control Tower, and estates remain mixed into
shared packages. Cleanup must preserve behavior and historical import paths.

~~~mermaid
flowchart TB
  apps[Apps: Tower, readiness, pilot, CLIs and tools] --> estates[Estates: CardDemo, CloudBank, iDempiere, T-SQL, CMS]
  estates --> engine[Engine: factory, workflow, execution, graph and agents]
  engine --> core[Core: common, evidence, trust and judge]
~~~

Dependencies may point down this diagram. The judge must depend only on core;
extracting trust and removing upward imports are separate A2 work.
The diagram is a target, not a claim that today's imports satisfy it.

## Package map

These are existing locations. Proposed trust and estate namespaces will be
introduced with compatibility shims rather than changing old commands.

| Target | Existing package | Responsibility |
| --- | --- | --- |
| Core | [lightyear_common](src/lightyear_common/) | Shared runtime and command support. |
| Core | [lightyear_evidence](src/lightyear_evidence/) | Evidence contracts and proof utilities. |
| Core | [lightyear_judge](src/lightyear_judge/) | Authoritative comparison and receipt verification. |
| Engine | [lightyear_factory](src/lightyear_factory/) | Planner, Builder and Analyst orchestration. |
| Engine | [lightyear_workflow](src/lightyear_workflow/) | Resumable workflow and run history. |
| Engine | [lightyear_execution](src/lightyear_execution/) | Execution backends and containment. |
| Engine | [lightyear_knowledge_graph](src/lightyear_knowledge_graph/) | Source graph and retrieval. |
| Engine | [lightyear_business_rules](src/lightyear_business_rules/) | Rule contracts and analysis. |
| Engine | [lightyear_runtime](src/lightyear_runtime/) | Runtime evidence and adapters. |
| Engine | [lightyear_agent](src/lightyear_agent/) | Agent-facing workflow transport. |
| Engine | [lightyear_audit](src/lightyear_audit/) | Auditable analysis and replay. |
| Engine, proposed | [lightyear_cloud_runner](src/lightyear_cloud_runner/) | Cloud execution; review the layer in A2. |
| Engine, proposed | [extension runtime](extensions/runtime/) | Extension implementation; review in A2. |
| Estates | [lightyear_mainframe](src/lightyear_mainframe/) | Mainframe source and twin tooling. |
| Estates | [lightyear_calibration](src/lightyear_calibration/) | Native calibration and iDempiere campaigns. |
| Estates | [carddemo_oracle](src/carddemo_oracle/) | Retained Python second opinion; not the sole authority for new expected answers. |
| Mixed; split in A3 | [lightyear_data](src/lightyear_data/) | Generic migration plus CloudBank, T-SQL and estate logic. |
| Apps | [lightyear_control_tower](src/lightyear_control_tower/) | Operator UI; also holds trust code to extract. |
| Apps | [lightyear_pilot](src/lightyear_pilot/) | Pilot planning and reporting. |
| Apps | [lightyear_readiness](src/lightyear_readiness/) | Readiness views and checks. |
| Apps | [lightyear_qualification](src/lightyear_qualification/) | Qualification interfaces. |
| Apps | [lightyear_toolkit](src/lightyear_toolkit/) | Public verifier tooling and MCP. |

## Data and trust flow

The legacy INTCALC preview, gate and freeze entry points consult the pinned
retirement registry before any execution, credential prompt or admission. Their
current lineage is closed; CI retirement-refusal evidence is not qualification.
Historical receipts remain readable. A future reference-backed gate requires a
separate reviewed implementation; no registry or environment override admits it.

Estate source → knowledge graph → agents → candidate → judge against the answer
key → receipt → human signature in the Factory Tower. The graph supplies source
context; agents cannot change the answer key or promote their own verdicts.
The private verifier gateway must return only approved redacted feedback.
The public [reference qualification tool](tools/intcalc_reference_execution.py)
compares original COBOL execution, independent public derivations and the retained
Python oracle. Reference image and profile qualification remain prerequisites;
this tool does not admit candidates, freeze answers or handle a private seed.
A separate provisional comparison builds the same-job image and requires a
reviewed package and library inventory match before public probes or cases. Its
reports are explicitly provisional and unqualified; it cannot freeze answers
or satisfy the published-image qualification path.

Trust lives in the hash-chained decision journal, controlled signing keys, input
hashes and verified receipts. The Tower is the interface to that authority; its
screen state is not an approval. Signatures verify against the trusted journal
and exact request, scope, executable head and validity window.
The proposed lightyear_trust package owns these primitives independently of UI.
The judge may consume core contracts and explicit input data; it must not import
agent orchestration, UI state, estate policy or graph lookups to decide a verdict.

## Evidence and compatibility

Keep dated receipts and signed evidence immutable. New large evidence belongs in
Release assets with committed hashes and inventories; tracked archives remain
historical evidence. Never rewrite Git history. See
[retained evidence](docs/receipts/) and [Factory records](docs/factory/).

Do not move plan-bound paths before the live POSTTRAN window closes or the attempt
is consumed. Preserve old imports and commands with deprecation shims until all
citing dated receipts have been superseded. No shim retirement date is set.
A2 enforces layers; A3 separates estates; A4 bounds new large files; A5 consolidates
entry points; A6 applies lint and size controls to changed code.

The provisional reference comparison separates only five exact declared-file implicit CLOSE diagnostics from compared stderr. Raw stderr and the extracted diagnostics remain public evidence; all other stderr bytes remain compared. Revised probe expectations require a fresh independent review before dispatch.

Reference domain restriction adopted by Howard on 16 November 2026
([decision](spec/reference-execution/2026-11-16-preferred-signs-r1/HOWARD-DECISION-20261116.md#sha256=6f12d921e95d875acee50ccf27f08356a79aa87e05cf8374e962218dbf2c13a2)):
`REFERENCE_LIMIT_PREFERRED_SIGNS` confines the GnuCOBOL reference to signed zoned
input fields with preferred C and D signs. Zone-F signed inputs are outside its proven
domain and need mainframe evidence. The byte bridge checks every signed zoned
input field before loading indexed files. The zoned-signs-2 IBM expectation stays
unchanged; a hash-bound reference finding preserves the actual difference in
reports rather than calling it a match. This is an open-source reference, not
mainframe-proven. No freeze or dispatch follows from this proposal.

Planned: the opt-in legacy graph boundary rebuilds a reviewed public-source projection before G2 indexing. Planner and Builder receive only four bounded read methods over that exact approved snapshot; modern and test material, verification links and hidden-result provenance are excluded. Existing G2 signatures and Tower approval remain required. The standalone boundary has no model caller or activation path; later controller and accounting patches are separately reviewed.
