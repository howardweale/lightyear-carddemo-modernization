# LIGHTYEAR governed pilot work package

**Package identity:** `2ca8ba7ab2412e84558f9eeab0e4361e28f2f5d7d331c2d81acb172a76913aa0`

## Outcome

LIGHTYEAR can turn one recorded human pilot selection into a deterministic, graph-scoped, multi-technology development work package.

This package is ready for human-governed work-order authoring. It cannot dispatch the factory, authorize native execution, or approve production.

## Development cells

| Cell | Technology | Risk | Source files | Dependencies | Dispatch ready |
|---|---|---|---:|---:|---:|
| `cell:carddemo-account-mixed-language-pilot-v0-33:cobol` | COBOL | high | 2 | 2 | no |
| `cell:carddemo-account-mixed-language-pilot-v0-33:db2` | Db2 | high | 3 | 0 | no |
| `cell:carddemo-account-mixed-language-pilot-v0-33:hlasm` | HLASM | high | 1 | 0 | no |
| `cell:carddemo-account-mixed-language-pilot-v0-33:jcl` | JCL | high | 1 | 2 | no |
| `cell:carddemo-account-mixed-language-pilot-v0-33:pl-i` | PL/I | high | 1 | 1 | no |

## Planning waves

- **Wave 0 — boundary-disposition-verification:** passed; automatic dispatch is disabled.
- **Wave 1 — bounded-work-order-authoring:** ready-for-human-governed-authoring; automatic dispatch is disabled.
- **Wave 2 — integrated-development-proof:** blocked-until-cell-evidence-passes; automatic dispatch is disabled.
- **Wave 3 — authorized-native-validation:** blocked-no-mainframe-access; automatic dispatch is disabled.

## Limitations

- Cells are bounded draft scopes, not signed or admitted factory work orders.
- No candidate, behavior comparison, model qualification, or native execution is created by packaging.
- Every cell retains a separate live-evidence backlog and remains blocked from production promotion.
