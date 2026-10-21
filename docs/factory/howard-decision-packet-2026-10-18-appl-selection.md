# Howard decision packet: APPL-RESULT selection addendum

APPL-RESULT selection as of 2026-10-18. Unsigned; no authority inferred.

| Program | Selected contract | Members | Template queue ID | Class proof | Re-review required |
|---|---|---:|---|---|---|
| INTCALC | [intcalc-02-appl-result-class-request-2026-10-17.json](intcalc-02-appl-result-class-request-2026-10-17.json) | 81 | `factory-550f6ed38a9e8863b959b294af3c61cc91c97f11eff17e324a3476d39bed237e` | `e054defd96b168cc73a154fec1492f96c001c91f8c277737c3db78d08ae584a8` | True |
| POSTTRAN | [contract.json](appl-result-signing-2026-10-16/POSTTRAN/contract.json) | 96 | `factory-92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1` | `13aca947966f508c373d9a1269e4729b744549c6e1fbb32f205a6543dd38a242` | False |

INTCALC position 2 is a template: binding the verified position-1 decision changes its final queue hash. The final bound hash must be checked before import.

INTCALC: Ordered position 2 is the only class request that contributes to request 06; its retained reference census has a different binding from the October 16 human sample packet.
POSTTRAN: No ordered POSTTRAN APPL-RESULT request exists in the inspected committed signing inventories; retain the existing 96-member contract unchanged.

[Current signing guide](appl-result-signing-2026-10-18.md). INTCALC requires re-review of the changed class-proof binding before signing. POSTTRAN retains its old evidence bindings. No signature, import, activation, release or Phase 2 execution is performed or authorized by this addendum. Other decision gates remain in the measured verdict and ordered packet.
