# APPL-RESULT signing guide: October 18 supersession

APPL-RESULT selection as of 2026-10-18. Unsigned; no authority inferred.

| Program | Selected contract | Members | Template queue ID | Class proof | Re-review required |
|---|---|---:|---|---|---|
| INTCALC | [intcalc-02-appl-result-class-request-2026-10-17.json](intcalc-02-appl-result-class-request-2026-10-17.json) | 81 | `factory-550f6ed38a9e8863b959b294af3c61cc91c97f11eff17e324a3476d39bed237e` | `e054defd96b168cc73a154fec1492f96c001c91f8c277737c3db78d08ae584a8` | True |
| POSTTRAN | [contract.json](appl-result-signing-2026-10-16/POSTTRAN/contract.json) | 96 | `factory-92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1` | `13aca947966f508c373d9a1269e4729b744549c6e1fbb32f205a6543dd38a242` | False |

INTCALC position 2 is a template: binding the verified position-1 decision changes its final queue hash. The final bound hash must be checked before import.

INTCALC: Ordered position 2 is the only class request that contributes to request 06; its retained reference census has a different binding from the October 16 human sample packet.
POSTTRAN: No ordered POSTTRAN APPL-RESULT request exists in the inspected committed signing inventories; retain the existing 96-member contract unchanged.

This dated guide supersedes the October 17 handoff instructions. The old guide,
contracts and thirty-member audit samples remain unchanged historical evidence.
The retired INTCALC standalone contract cannot contribute to ordered request 06.
The selected ordered class proof is the reference census bound by that packet;
it is not the historical class-proof wrapper. Howard must re-review this binding
before signing: the October 16 sample review does not transfer to different
proof bytes, and the ordered request does not bind those old sample/audit files.
POSTTRAN keeps its original contract and sample bindings. The inspected October
18 inventories contain no ordered POSTTRAN APPL-RESULT counterpart.

## Import preconditions

Use only the existing Windows Factory root and service on port 8769. Never
create another root, reset journal trust, or use the B06 service on port 8768.
First obtain Howard's approval of the final green implementation and merge it.
Then review the selected evidence, export the existing Factory journal, and
independently verify its current head and public key. A public snapshot or a
hash supplied by the proof itself is not an independent trust anchor.

For INTCALC, position 1 must be decided before position 2 can be bound. Preserve
the original template. Publish the new unsigned, predecessor-bound request for
review through the ordered signing process; verify its new file and queue
hashes. Do not import the unbound template or the retired standalone contract.
For POSTTRAN, use the selected unchanged file and verify the full queue hash.
Both imports now require `--journal`, `--public-key` and `--trusted-head` in
addition to `--repository`, `--root` and `--contract`. No command reads a private
key. This guide performs no import, signature, activation or Phase 2 execution.

## Content supersession

The importer compares the program and full item set, independent of JSON
formatting and unrelated fields. Previously decided content also requires an
explicit successor. A successor contract must carry a `supersession` source
reference to a committed `docs/factory/appl-result-supersession-YYYY-MM-DD*.json`
record. That record must bind the item set, predecessor normalized contract,
latest decision hash (if one exists), successor normalized contract and date.
Its exact bytes and Git commit are checked before any import write. The
normalized hash excludes only the reference itself and its identical source
entry, and the externally bound predecessor decision. All other bytes remain
bound. A record cannot create acceptance or carry a signature forward.
