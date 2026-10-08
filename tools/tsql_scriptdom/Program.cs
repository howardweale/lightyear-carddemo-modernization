// Private local stdin/stdout bridge; no database, model, or network code.
using System.Collections;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.SqlServer.TransactSql.ScriptDom;

Console.InputEncoding = new UTF8Encoding(false);
Console.OutputEncoding = new UTF8Encoding(false);
var source = Console.In.ReadToEnd();
if (Encoding.UTF8.GetByteCount(source) > 1024 * 1024) return 2;
var parser = new TSql160Parser(initialQuotedIdentifiers: true);
var fragment = parser.Parse(new StringReader(source), out IList<ParseError> errors);
var nodes = new List<object>();
var seen = new HashSet<TSqlFragment>(ReferenceEqualityComparer.Instance);
var statements = new List<object>();
var branches = new List<object>();
var handlers = new List<object>();
var excludedDeclarations = new List<object>();
var procedureContracts = new List<object>();
var dependencies = new List<object>();
var nondeterministic = new HashSet<string>();
var generator = new Sql160ScriptGenerator();
object Span(TSqlFragment f) => new { start_utf16=f.StartOffset, length_utf16=f.FragmentLength, line=f.StartLine };
int procedures = 0;
void Walk(TSqlFragment f) {
    if (!seen.Add(f)) return;
    if (seen.Count > 100000) throw new InvalidDataException("AST limit");
    string kind = f.GetType().Name;
    if (kind is "CreateProcedureStatement" or "CreateOrAlterProcedureStatement" or "AlterProcedureStatement") procedures++;
    if (f is ProcedureStatementBody proc) {
        var name=proc.ProcedureReference.Name;
        procedureContracts.Add(new { schema=name.SchemaIdentifier?.Value ?? "dbo", name=name.BaseIdentifier.Value,
            parameters=proc.Parameters.Select(p => {
                generator.GenerateScript(p.DataType,out string type);
                return new { name=p.VariableName.Value, type, output=p.Modifier.ToString()=="Output", has_default=p.Value is not null };
            }).ToArray() });
    }
    if (f is NamedTableReference table) {
        var name=table.SchemaObject;
        dependencies.Add(new { kind="table-or-view", parts=name.Identifiers.Select(i=>i.Value).ToArray(),
            cross_database=name.DatabaseIdentifier is not null || name.ServerIdentifier is not null });
    }
    if (f is FunctionCall call && new[]{"GETDATE","SYSDATETIME","GETUTCDATE","SYSUTCDATETIME","NEWID","RAND"}.Contains(call.FunctionName.Value.ToUpperInvariant()))
        nondeterministic.Add(call.FunctionName.Value.ToUpperInvariant());
    // AST spans use UTF-16 offsets, explicitly declared; no source literals/errors echoed.
    nodes.Add(new { kind, start_utf16 = f.StartOffset, length_utf16 = f.FragmentLength, line = f.StartLine });
    bool declarationWithoutRuntimeStatement = f is DeclareTableVariableStatement
        || (f is DeclareVariableStatement d && d.Declarations.All(v => v.Value is null));
    if (declarationWithoutRuntimeStatement)
        excludedDeclarations.Add(new { kind, span=Span(f), reason="declaration-without-XE-executable-statement; native controls required" });
    if (f is TSqlStatement && !declarationWithoutRuntimeStatement && kind is not ("CreateProcedureStatement" or "CreateOrAlterProcedureStatement" or "AlterProcedureStatement"
          or "CreateTriggerStatement" or "CreateOrAlterTriggerStatement" or "AlterTriggerStatement"
          or "BeginEndBlockStatement" or "TryCatchStatement"))
        statements.Add(new { kind, start_utf16=f.StartOffset, length_utf16=f.FragmentLength, line=f.StartLine });
    if (f is IfStatement iff)
        branches.Add(new { kind="if", condition=Span(iff.Predicate), statement=Span(iff),
            then_span=Span(iff.ThenStatement), else_span=iff.ElseStatement is null ? null : Span(iff.ElseStatement) });
    if (f is WhileStatement loop)
        branches.Add(new { kind="while", condition=Span(loop.Predicate), statement=Span(loop),
            then_span=Span(loop.Statement), else_span=(object?)null });
    if (f is TryCatchStatement tc)
        handlers.Add(new { kind="catch", span=Span(tc.CatchStatements) });
    foreach (var p in f.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)) {
        if (!p.CanRead || p.GetIndexParameters().Length != 0 || p.Name == "ScriptTokenStream") continue;
        var value = p.GetValue(f);
        if (value is TSqlFragment child) Walk(child);
        else if (value is IEnumerable list && value is not string)
            foreach (var item in list) if (item is TSqlFragment element) Walk(element);
    }
}
Walk(fragment);
var payload = new {
    schema = "tsql-scriptdom/1",
    input_sha256 = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(source))).ToLowerInvariant(),
    parsed = errors.Count == 0, procedure_count = procedures,
    version = typeof(TSql160Parser).Assembly.GetName().Version!.ToString(),
    errors = errors.Select(e => new { number = e.Number, line = e.Line, column = e.Column }),
    ast_nodes = nodes,
    semantic_catalogue = new { schema="tsql-scriptdom-semantics/1", procedures=procedureContracts,
        dependencies, nondeterministic_functions=nondeterministic.OrderBy(x=>x).ToArray(),
        dependency_closure="partial; native catalogue closure required" },
    coverage_catalogue = new { schema="tsql-scriptdom-coverage/1", statements, branches, handlers,
        excluded_declarations=excludedDeclarations,
        scope="procedural statements, IF/WHILE edges and CATCH paths; SQL expression branches excluded" }
};
Console.WriteLine(JsonSerializer.Serialize(payload));
return errors.Count == 0 ? 0 : 1;
