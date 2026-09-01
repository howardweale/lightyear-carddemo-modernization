# Third-party notice

This prototype models the `INTCALC` workload from AWS Samples CardDemo:

- Repository: https://github.com/aws-samples/aws-mainframe-modernization-carddemo
- Pinned commit: `59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e`
- Upstream licence: Apache License 2.0

The distributed starter does not bundle the upstream repository. Its source model, field layouts,
and documentation link to the upstream Apache-licensed source and copybooks. Preserve upstream
copyright and licence notices if you later copy CardDemo source or data into this project.

The Control Tower bundles Latin-1 webfont subsets from IBM Plex:

- Repository: https://github.com/IBM/plex
- Families: IBM Plex Sans and IBM Plex Mono
- Upstream licence: SIL Open Font License 1.1
- Bundled licence: `knowledge/viewer/fonts/IBM-PLEX-LICENSE.txt`

The fonts are served locally so the Control Tower makes no Google Fonts request and remains usable
in air-gapped customer environments.
