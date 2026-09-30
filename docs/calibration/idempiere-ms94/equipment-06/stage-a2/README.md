# Equipment 06, Stage A′2: prospective diagnostic qualification

This qualification has 18 fresh Oracle/PostgreSQL pairs: six planted faults,
each repeated three times. It makes zero model calls and gives no autonomous
success credit. Execution is sequential, with an eight-hour cap and a stop on
the first unexpected outcome. There are no restart or replacement slots.

| Planted control | Required result in both engines |
|---|---|
| Nonempty reversal-allocation fact assertion | Candidate / reversal allocation / `AssertionError`, exact candidate frame |
| Null dereference on an unloaded invoice | Candidate / invoice / `NullPointerException`, exact candidate frame |
| Shipment constructor rejects an incompatible document type | Application / shipment / `AdempiereException`, exact candidate frame |
| Test-only JourneySupport throw | Execution failure, no diagnostic, `halted-equipment-suspect` |
| Omitted post-rollback observation wait | Contract violation, missing public rollback witness |
| Nonnumeric public `order.id` | Contract violation, invalid public identifier |

The candidate sources are constructed from the retained reference. Only the
support-fault test changes its private assembled copy of support; the accepted
public support file and every inherited A1 source remain byte-identical. Source
construction manifests declare the expected result before execution. Compilation
and unit checks are preparation evidence, not native qualification or independent
human source attestation.

The unchanged A1 judge determines the native class. The pinned runtime exporter
adds only closed exception provenance, candidate-frame and public-stage fields;
exception messages and private values are excluded. Support or outside-candidate
throws suppress feedback and receive an equipment-suspect disposition. They do
not automatically void a cohort. Missing or corrupt equipment evidence retains
its equipment-failure path.

Each native archive is signed and replayed with the frozen A2 publication tool,
which checks the complete gate, diagnostic bytes, suspect flag and disposition.
After termination, a separate replay and actual owned Docker inventory check are
required. Only safe signed metadata is published; native archives stay local.

The plan binds the successful A1 report and its independent terminal verification,
as well as Howard Weale's accepted B03 operator adjudication. A2 alone does not
admit B04: A3 must still establish byte-identical diagnostics on native runs
against a second checkpoint with perturbed private values and identifiers. No
B04 model call is permitted until all prerequisites and the new public freeze
are complete. B03's 12/20 result and all earlier costs remain separate.

This is a prospective declaration, not an A2 pass claim. The exact plan,
declaration and snapshot manifest are published before the one-shot launch.
