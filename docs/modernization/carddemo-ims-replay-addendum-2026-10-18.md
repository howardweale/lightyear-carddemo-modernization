# IMS replay scope correction — 2026-10-18

The earlier replay counted every supported case as adapter coverage. PROCOPT, SENSEG and invalid SSA responses are decided inside the replay. New schema `carddemo-typed-ims-replay/2` separates those local answers from calls exercising the typed PostgreSQL adapter, with matched counts for each and unsupported cases retained in the total. Fixture creation and after-state inspection do not earn adapter-call credit.

GN/GHN now use the adapter's full two-level preorder rather than filtering to roots. Original case IDs and historical status expectations remain preserved; case 02's old root-sequence name no longer describes its returned child. Returned-segment expectations come from the explicit synthetic hierarchy, independently of adapter iteration. Supplementary cases exercise the second child and the child under the next parent, including hold traversal. Full returned bytes and database after-state are compared.

The historical corpus and receipts remain unchanged. CI emits the new measured counts and summary; tests alter the scope/result input and require summary changes. This remains synthetic two-level twin evidence, not native IMS or full textual SSA grammar proof.
