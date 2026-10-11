# Systematic survivor review and compiler refusals

Observed code: `3283265d71e268b3dc66b09fb2808e72a18b19ac`. [Compiled run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38154818763).

The measured campaign has zero unexplained INTCALC survivors and three POSTTRAN survivors, each with an individual post-campaign source/runtime argument. Raw statuses remain unchanged. Every killed mutant and every listed argument is retained in the program JSON records. Compiler refusals remain a separate failure bucket in both denominators. No operator acceptance or release is claimed.

## INTCALC

No unexplained survivors remain after the listed review.

No additional post-campaign argument was required.

Compiler refusals: `CBACT04C-receiving-size-131-17`, `CBACT04C-constant-638-379`, `CBACT04C-constant-638-381`, `CBACT04C-constant-645-391`, `CBACT04C-constant-645-393`.

## POSTTRAN

No unexplained survivors remain after the listed review.

Additional post-campaign source/runtime arguments (raw status remains survived): `CBTRN02C-delete-MOVE-209-47`, `CBTRN02C-delete-MOVE-557-314`, `CBTRN02C-CVACT03Y-receiving-scale-7-4`.

Compiler refusals: `CBTRN02C-receiving-size-140-11`, `CBTRN02C-constant-414-207`, `CBTRN02C-constant-717-440`, `CBTRN02C-constant-717-442`, `CBTRN02C-constant-724-452`, `CBTRN02C-constant-724-454`.

