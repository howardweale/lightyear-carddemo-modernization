# Beginner developer quickstart

## What you are running

The source-only pilot reads an approved folder of source text and produces an inventory plus an
evidence dossier. It never logs into a mainframe, compiles the original programs, changes source,
or claims that the modernized candidates are production-equivalent.

## Five-minute path

1. Install Python 3.11 or newer.
2. From the repository root, run `./source-only-pilot.sh doctor`.
3. Run `./source-only-pilot.sh rehearse` to process the safe reference intake.
4. Open `work/source-only-pilot/pilot.dossier.md`.
5. Run `./lightyear.sh explorer` to inspect the composite graph in a browser.

The dossier should say:

- `pilot_ready: true`;
- `model_qualified: false`;
- `mainframe_equivalent: false`;
- `production_ready: false`.

Those false values are not failures. They are the honest result until authorized original-system
execution and independent live comparison exist.

## Using an approved source folder

Ask the source owner for a written pilot approval identifier. Ensure the directory contains only
approved source and configuration text—never credentials, binaries, data dumps, listings with
customer records, or runtime output. Then run:

```bash
./source-only-pilot.sh intake /approved/source APPROVAL-ID work/customer-pilot
./source-only-pilot.sh preflight work/customer-pilot
./source-only-pilot.sh dossier work/customer-pilot
```

If intake fails, fix the reported file or request a deliberate profile change. Do not rename a
binary or credential file to make it pass.
