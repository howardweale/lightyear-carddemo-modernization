# CardDemo data component proof

Scope: public-source-and-generated-twin. Overall verdict: **indeterminate**.

| File | Input | Loaded | Quarantined | Round trip | Reconciliation | Browse |
| --- | ---: | ---: | ---: | --- | --- | --- |
| acctdata | 50 | 50 | 0 | 50/50 equivalent | equivalent | 212/212 equivalent |
| custdata | 50 | 50 | 0 | 50/50 equivalent | equivalent | 212/212 equivalent |
| carddata | 50 | 50 | 0 | 50/50 equivalent | equivalent | 540/540 equivalent |
| cardxref | 50 | 50 | 0 | 50/50 equivalent | equivalent | 540/540 equivalent |
| usrsec | 10 | 10 | 0 | 10/10 equivalent | equivalent | 56/56 equivalent |

IMS generated traversal: equivalent. Public IMS unload and DL/I replay: indeterminate.

Screens: zero sessions compared; mutation catch rate not measured. No z/OS or customer-release claim.

Quarantined records require review. The receipt is unsigned and does not authorize release.

Measured in [CI run 38816713103](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38816713103) at `aad91e37a4b84d0d92c9cd886bb44d5a0915c036`.

The JSON is an explicitly derived summary. The original full receipt is 1,230,556 bytes and remains in the CI artifact and local staging pending the designated retention-store location. Generated mappings and DDL are retained alongside this report.

This delivers the bounded data-migration component. REDEFINES requires a reviewed discriminator/live-reader policy and is refused; unresolved IMS relationships, utility-unload framing, full DL/I compatibility and the Java access API remain open. No screen or customer-release claim is made.
