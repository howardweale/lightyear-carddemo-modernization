# ScriptDom stdin bridge

Build verified on the approved Ubuntu 24.04 x86_64 VM on October 7, 2026: all 42 source procedures parsed. No database, model or container calls are made by the parser bridge.

The .NET 8 project references Microsoft.SqlServer.TransactSql.ScriptDom
161.8901.0 and selects TSql160Parser. Source is accepted on UTF-8 stdin (maximum
1 MiB); one JSON object is written on stdout. It contains the input SHA-256,
parser assembly version, parse error codes/locations and AST kind/span records.
Offsets are UTF-16, as used by ScriptDom. Source literals and error messages are
not echoed.

Exit 0 means syntactic parse completed without errors, not that SQL is supported
or behavior is equivalent. A procedure count of zero is not admitted by the
Python client. The client also rejects missing AST nodes and a mismatched input
hash. The bridge must be a trusted operator-installed executable.

The VM build used .NET SDK 8.0.131 and completed with zero warnings/errors.
The report, assembly and lock-file hashes were independently read back from the
VM and are listed in [native results](../../data-modernization/tsql-procedures/native-results.md).
Build artifacts stay outside source control.

The coverage revision additionally emits executable statement spans, IF/WHILE
edges, CATCH spans and `excluded_declarations`. Uninitialized scalar declarations
and table-variable declarations are recorded separately because SQL Server does
not emit standalone statement events for them. Initialized declarations remain
measured. Native coverage controls test both exclusions; see the
[coverage contract](../../data-modernization/tsql-procedures/coverage-and-mappings.md)
and [new results](../../data-modernization/tsql-procedures/coverage-results.md).
The original parser build and the coverage bridge are separate hash-bound builds.

For a fresh approved build environment:

```sh
dotnet restore tools/tsql_scriptdom/TsqlInventory.csproj
dotnet build tools/tsql_scriptdom/TsqlInventory.csproj --no-restore -c Release
```

Review and retain the resolved package lock and hash the actual bridge/runtime
before binding a new build. A package/compiler failure cannot be replaced by the
lexical scanner. Successful parsing does not qualify database semantics.
