# COACTUP phone and date validation

This bounded Java group replaces three production statement ranges: the complete
phone validator, date validator, and date-of-birth check. `AccountPhoneDateModel`
retains the frozen generator's storage and condition data, copies the model, and
removes exactly those three executable bodies before account-service execution.
`AccountEditState` is a closed field/flag interface; the phone and date rule classes
do not inspect JSON or execute statement nodes. Input orchestration, rendering,
and other account work still use the existing statement engine. COACTUPC is not
a completed idiomatic screen.

The scope manifest inventories every physical paragraph in COACTUPC and the date
COPY, including internal EXIT labels. The phone shortcut repeats the source's
NUMA-space operand; first-error ordering, all component flags, numeric scratch,
leap-year divisor/remainder, LE feedback, and strict-before-today DOB behavior are
preserved. The existing declared Gregorian LE adapter remains a shared dependency,
not native LE evidence.

CI must pass both the unchanged full-slice workflow (independent raw-source API,
browser, complete database and mutation proof) and the additional phone/date
workflow. Supplemental fixtures compare all storage bytes and scalar values to
original statement execution, including exceptional outcomes and forced nonzero
LE feedback. A seeded storage mismatch must fail. The added mutation gate requires
nonempty reports and at least 90% KILLED for each of four new classes; every mutant
status remains in its denominator. This adds no credit to historical receipts.

The binding generator, original proof workflow, receipt, Maven configuration,
existing Java tests and both freeze manifests remain unchanged. No local runtime,
model calls, signatures, imports, activation or production acceptance are claimed.
Fresh CI evidence must be reviewed before exact-head merge approval.
