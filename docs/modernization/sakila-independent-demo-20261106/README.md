# Sakila independent two-view draft

Planned comparison: the SQL Server and PostgreSQL ports of `customer_list` and `sales_by_store` from [jOOQ/sakila](https://github.com/jOOQ/sakila/tree/e089a5b1ec9af0df7a9c6a5d47d49fa1736a4e84), originally by Mike Hillyer and ported by DB Software Laboratory. Lightyear did not author the ports. The preserved snippets retain upstream byte hashes and BSD attribution.

Planned inputs: verifier-authored minimal dependency tables, active/inactive customers, duplicate customer and store/manager display names, two stores (the second has no customer membership), NULL phone, and exact decimal payments. These are public synthetic rows, not the upstream full database or customer data.

Planned reporting: strict schema compares original ordered names/types, including `zip_code` versus `zip code`, ID/SID case, and SQL Server's extra `store_id`. A separate explicit common-field mapping preserves duplicate rows, NULL and exact decimals. No silent renaming or column removal applies to strict results.

Planned negative controls: an active-predicate flip and removal of payment 4 from the duplicate-name second store, on fresh fixtures. Both are verifier-authored sensitivity controls, not upstream defects. Unit fixtures are synthetic capture documents, not database observations.

Not yet executed: database capture or native engine validation. Missing/failed capture is insufficient evidence. The immutable image identities and input hashes are in `run-packet.json` and the input manifest. SQL Server Developer license acceptance and a confirmed zero-cost standard CI allowance require Howard's separate exact-packet approval; Not yet accepted: SQL Server EULA.

Planned CI sequence and stop conditions are in the packet. No capture workflow is enabled by this draft. The comparator's CI unit tests exercise parsing and controls only; they do not demonstrate engine behavior. Scope excludes arbitrary SQL, stored procedures, performance and customer qualification.
