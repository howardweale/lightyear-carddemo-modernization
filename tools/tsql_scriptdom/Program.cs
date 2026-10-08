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
var nodeIds = new Dictionary<TSqlFragment,int>(ReferenceEqualityComparer.Instance);
var statements = new List<object>();
var branches = new List<object>();
var handlers = new List<object>();
var excludedDeclarations = new List<object>();
var procedureContracts = new List<object>();
var dependencies = new List<object>();
var resultContracts = new List<object>();
var updateJoins = new List<object>();
var nondeterministic = new HashSet<string>();
var generator = new Sql160ScriptGenerator();
object Span(TSqlFragment f) => new { start_utf16=f.StartOffset, length_utf16=f.FragmentLength, line=f.StartLine };
int procedures = 0;
void Walk(TSqlFragment f, TSqlFragment? parent=null) {
    if (!seen.Add(f)) return;
    if (seen.Count > 100000) throw new InvalidDataException("AST limit");
    nodeIds[f]=seen.Count;
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
    if (f is SelectStatement select && select.QueryExpression is QuerySpecification query && !query.SelectElements.Any(e=>e is SelectSetVariable)) {
        var outputNames=query.SelectElements.Select(e=>e is SelectScalarExpression scalar ? scalar.ColumnName?.Value ?? (scalar.Expression as ColumnReferenceExpression)?.MultiPartIdentifier?.Identifiers.LastOrDefault()?.Value : null).ToArray();
        var keys=new List<int>();bool resolved=true;
        foreach(var order in query.OrderByClause?.OrderByElements ?? new List<ExpressionWithSortOrder>()) {
            int index=-1;
            if(order.Expression is IntegerLiteral ordinal && int.TryParse(ordinal.Value,out int n))index=n-1;
            else if(order.Expression is ColumnReferenceExpression column) {
                var name=column.MultiPartIdentifier?.Identifiers.LastOrDefault()?.Value;
                var matches=outputNames.Select((value,i)=>(value,i)).Where(x=>name is not null && string.Equals(x.value,name,StringComparison.OrdinalIgnoreCase)).ToArray();
                if(matches.Length==1)index=matches[0].i;
            }
            if(index<0 || index>=outputNames.Length)resolved=false;
            keys.Add(index);
        }
        resultContracts.Add(new { start_utf16=select.StartOffset, ordered=query.OrderByClause is not null, key_indices=keys, resolved });
    }
    if(f is UpdateSpecification update && update.FromClause?.TableReferences.Count==1 && update.FromClause.TableReferences[0] is QualifiedJoin join && join.FirstTableReference is NamedTableReference left && join.SecondTableReference is NamedTableReference right) {
        var equalities=new List<string[][]>();bool closed=true;
        void Equalities(BooleanExpression expression) {
            if(expression is BooleanBinaryExpression binary && binary.BinaryExpressionType==BooleanBinaryExpressionType.And) {Equalities(binary.FirstExpression);Equalities(binary.SecondExpression);}
            else if(expression is BooleanComparisonExpression comparison && comparison.ComparisonType==BooleanComparisonType.Equals && comparison.FirstExpression is ColumnReferenceExpression a && comparison.SecondExpression is ColumnReferenceExpression b) {
                equalities.Add(new[]{a.MultiPartIdentifier.Identifiers.Select(x=>x.Value).ToArray(),b.MultiPartIdentifier.Identifiers.Select(x=>x.Value).ToArray()});
            } else closed=false;
        }
        Equalities(join.SearchCondition);
        object Table(NamedTableReference t)=>new {parts=t.SchemaObject.Identifiers.Select(x=>x.Value).ToArray(),alias=t.Alias?.Value ?? t.SchemaObject.BaseIdentifier.Value};
        updateJoins.Add(new {start_utf16=update.StartOffset,target=(update.Target as NamedTableReference)?.SchemaObject.Identifiers.Select(x=>x.Value).ToArray(),left=Table(left),right=Table(right),equalities,closed,join_type=join.QualifiedJoinType.ToString()});
    }
    if (f is NamedTableReference table) {
        var name=table.SchemaObject;
        dependencies.Add(new { kind="table-or-view", parts=name.Identifiers.Select(i=>i.Value).ToArray(),
            cross_database=name.DatabaseIdentifier is not null || name.ServerIdentifier is not null });
    }
    if (f is FunctionCall call && new[]{"GETDATE","SYSDATETIME","GETUTCDATE","SYSUTCDATETIME","NEWID","RAND","SYSDATETIMEOFFSET","NEWSEQUENTIALID","CRYPT_GEN_RANDOM"}.Contains(call.FunctionName.Value.ToUpperInvariant()))
        nondeterministic.Add(call.FunctionName.Value.ToUpperInvariant());
    if (kind=="ParameterlessCall") {
        var property=f.GetType().GetProperty("ParameterlessCallType");
        if(property?.GetValue(f)?.ToString()=="CurrentTimestamp") nondeterministic.Add("CURRENT_TIMESTAMP");
    }
    if(f is SchemaObjectName dependency && parent is not NamedTableReference) {
        dependencies.Add(new { kind="schema-object", parts=dependency.Identifiers.Select(i=>i.Value).ToArray(),
            cross_database=dependency.DatabaseIdentifier is not null || dependency.ServerIdentifier is not null });
    }
    if(f is FunctionCall function) {
        var fn=function.FunctionName.Value.ToUpperInvariant();
        if(fn=="ROW_NUMBER" || fn=="STRING_AGG" && function.GetType().GetProperty("WithinGroupClause")?.GetValue(function) is null) nondeterministic.Add(fn+"_ORDER_POLICY");
    }
    // AST spans use UTF-16 offsets, explicitly declared; no source literals/errors echoed.
    nodes.Add(new { kind, node_id=seen.Count, parent_id=parent is null ? (int?)null : nodeIds[parent], start_utf16 = f.StartOffset, length_utf16 = f.FragmentLength, line = f.StartLine });
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
        if (value is TSqlFragment child) Walk(child,f);
        else if (value is IEnumerable list && value is not string)
            foreach (var item in list) if (item is TSqlFragment element) Walk(element,f);
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
        dependencies, result_contracts=resultContracts, update_joins=updateJoins, nondeterministic_functions=nondeterministic.OrderBy(x=>x).ToArray(),
        dependency_closure="partial; native catalogue closure required" },
    coverage_catalogue = new { schema="tsql-scriptdom-coverage/1", statements, branches, handlers,
        excluded_declarations=excludedDeclarations,
        scope="procedural statements, IF/WHILE edges and CATCH paths; SQL expression branches excluded" }
};
Console.WriteLine(JsonSerializer.Serialize(payload));
return errors.Count == 0 ? 0 : 1;
