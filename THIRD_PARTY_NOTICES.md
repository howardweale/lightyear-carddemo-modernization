# Third-party notices

This file documents third-party reference material and attribution. It does not license
LIGHTYEAR's original source code.

This prototype models the `INTCALC` workload from AWS Samples CardDemo:

- Repository: https://github.com/aws-samples/aws-mainframe-modernization-carddemo
- Pinned commit: `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`
- Upstream licence: Apache License 2.0

The distributed starter does not bundle the upstream repository. Its source model, field layouts,
and documentation link to the upstream Apache-licensed source and copybooks. Generated evidence
packs can contain bounded CardDemo source excerpts. The exact Apache License 2.0 and upstream
NOTICE are preserved in `LICENSES/Apache-2.0.txt` and
`LICENSES/AWS-CardDemo-NOTICE.txt`.

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

## iDempiere release 13

The iDempiere reference-estate builder reads this pinned public source:

- Repository: https://github.com/idempiere/idempiere
- Pinned commit: `731515dcdd5278b843db33b9d3109d155b881951`
- Upstream license: GNU General Public License version 2
- Bundled license: `LICENSES/GPL-2.0-only.md`

The repository commits only a bounded summary inventory and projection. The complete Java
source-unit dependency inventory and graph are generated on demand under ignored `work/` output.
No iDempiere Java source body is committed by the full projection builder. If a complete generated
artifact is distributed separately, retain the source pin and GPL license and treat that artifact
as GPL-2.0-only to the extent it constitutes a work based on iDempiere.

## Oracle CloudBank v5

The CloudBank reference-estate builder reads this pinned public source:

- Repository: https://github.com/oracle/microservices-backend
- Pinned commit: `4f41b16d00c45503f691836fee8138010c969e86`
- Pinned subtree: `cloudbank-v5`
- Upstream license: Universal Permissive License 1.0
- Bundled license: `LICENSES/UPL-1.0.txt`

Copyright (c) 2021, 2023 Oracle and/or its affiliates.

The repository commits only a bounded summary inventory and projection. The complete tracked-file
and Java dependency projection is generated on demand under ignored `work/` output. If that output
is distributed separately, preserve the copyright notice above and the UPL license or reference.

Oracle, Java, MySQL, and NetSuite are registered trademarks of Oracle and/or its affiliates. Other
names may be trademarks of their respective owners. Oracle Corporation does not sponsor, endorse,
or certify LIGHTYEAR. Oracle names are used only to identify upstream software and compatibility
analysis.

## IBM Plex

The Control Tower bundles Latin-1 webfont subsets from IBM Plex:

- Repository: https://github.com/IBM/plex
- Families: IBM Plex Sans and IBM Plex Mono
- Upstream licence: SIL Open Font License 1.1
- Bundled licence: `knowledge/viewer/fonts/IBM-PLEX-LICENSE.txt`

The fonts are served locally so the Control Tower makes no Google Fonts request and remains usable
in air-gapped customer environments.
