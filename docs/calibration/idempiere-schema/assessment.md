# Native schema assessment

913 common base tables assessed; 0 one-sided foreign-key relationships and 0 nullability differences. Schema and application equivalence remain unproven.

Catalog matches describe declared properties only. Native behavioral probes and explicit domain rules remain required.

| Measurement | Count |
|---|---:|
| column declaration differences | 6268 |
| common base columns | 18852 |
| common base tables | 913 |
| default definition differences | 7720 |
| foreign key catalog matches | 3826 |
| foreign key enforcement differences | 0 |
| foreign key missing relationships | 0 |
| foreign key relationships | 3826 |
| key column order differences | 1 |
| nullable differences | 0 |
| primary key column set matches | 900 |
| unique key column set matches | 917 |
| unresolved dimensions | 10 |

## Foreign-key findings

| Relationship | Finding |
|---|---|

## Nullability findings

| Column | Oracle nullable | PostgreSQL nullable |
|---|---|---|

## Remaining schema obligations

- datatype-behavior: native-probes-required.
- defaults: native-probes-required.
- primary-unique-check-constraints: definition-and-negative-probes-required.
- indexes: definition-and-behavior-review-required.
- views: definition-and-behavior-review-required.
- routines: definition-and-behavior-review-required.
- triggers: definition-and-behavior-review-required.
- privileges: definition-and-behavior-review-required.
- row-policies: definition-and-behavior-review-required.
- sequences: definition-and-behavior-review-required.
