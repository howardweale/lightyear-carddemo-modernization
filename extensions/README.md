# Trusted extension foundation

MS #20 adds a versioned boundary for new evidence adapters and language packs without changing the
verified MS #19 graph in place. Adapter captures declare whether their evidence is `live`,
`recorded`, `simulated`, or `inferred`; bind every claim to one exact graph identity; retain only
bounded artifact metadata; and fail closed on missing entities, drift, tampering, or credential-
shaped fields.

The record/replay path never promotes trust. Replaying a live capture produces `recorded` evidence,
while simulated and inferred inputs retain their original classification.

The first language pack parses a bounded PL/I reference workload into a content-addressed graph
fragment. The fragment contributes PL/I programs, procedures, includes, file access, embedded Db2
SQL, and mixed-language calls. Cross-fragment references are resolved against the exact canonical
graph hash. A base-graph change invalidates the fragment until it is deliberately rebuilt.

```bash
./extension-foundation.sh verify
```

```powershell
.\extension-foundation.ps1 verify
```

The bundled PL/I and adapter captures are development fixtures. They do not claim customer source,
live z/OS observation, successful PL/I compilation, or production readiness.
