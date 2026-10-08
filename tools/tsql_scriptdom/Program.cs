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
var parents = new Dictionary<TSqlFragment,TSqlFragment?>(ReferenceEqualityComparer.Instance);
var nodeIds = new Dictionary<TSqlFragment,int>(ReferenceEqualityComparer.Instance);
var statements = new List<object>();
var branches = new List<object>();
var handlers = new List<object>();
var excludedDeclarations = new List<object>();
var procedureContracts = new List<object>();
var dependencies = new List<object>();
var execContracts = new List<object>();
var resultContracts = new List<object>();
var updateJoins = new List<object>();
var nondeterministic = new HashSet<string>();
var generator = new Sql160ScriptGenerator();
object Span(TSqlFragment f) => new { start_utf16=f.StartOffset, length_utf16=f.FragmentLength, line=f.StartLine };
int procedures = 0;
void Walk(TSqlFragment f, TSqlFragment? parent=null) {
    if (!seen.Add(f)) return;
    if (seen.Count > 100000) throw new InvalidDataException("AST limit");
    nodeIds[f]=seen.Count;parents[f]=parent;
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
    if (f is SelectStatement select) {
        bool inCursor=false,conditional=false;
        for(var ancestor=parent;ancestor is not null;ancestor=parents.GetValueOrDefault(ancestor)) {
            inCursor |= ancestor.GetType().Name.Contains("Cursor");
            conditional |= ancestor is IfStatement or WhileStatement or TryCatchStatement;
        }
        QueryExpression expression=select.QueryExpression;
        QueryExpression first=expression;
        while(true) {
            if(first is QueryParenthesisExpression paren)first=paren.QueryExpression;
            else if(first is BinaryQueryExpression binary)first=binary.FirstQueryExpression;
            else break;
        }
        var query=first as QuerySpecification;
        bool into=select.GetType().GetProperty("Into")?.GetValue(select) is not null;
        if(!inCursor && !into && (query is null || !query.SelectElements.Any(e=>e is SelectSetVariable))) {
            var outputs=query?.SelectElements.OfType<SelectScalarExpression>().ToArray() ?? Array.Empty<SelectScalarExpression>();
            var keys=new List<int>();bool resolved=query is not null && outputs.Length==query.SelectElements.Count;
            var order=expression.OrderByClause;
            if(order is null && expression is QueryParenthesisExpression qp)order=qp.QueryExpression.OrderByClause;
            foreach(var sort in order?.OrderByElements ?? new List<ExpressionWithSortOrder>()) {
                int index=-1;
                if(sort.Expression is IntegerLiteral ordinal && int.TryParse(ordinal.Value,out int n))index=n-1;
                else {
                    generator.GenerateScript(sort.Expression,out string orderText);
                    var matches=new List<int>();
                    for(int i=0;i<outputs.Length;i++) {
                        var output=outputs[i];generator.GenerateScript(output.Expression,out string outputText);
                        bool alias=sort.Expression is ColumnReferenceExpression c && c.MultiPartIdentifier.Identifiers.Count==1 &&
                            string.Equals(output.ColumnName?.Value,c.MultiPartIdentifier.Identifiers[0].Value,StringComparison.OrdinalIgnoreCase);
                        bool exactColumn=sort.Expression is ColumnReferenceExpression sc && output.Expression is ColumnReferenceExpression oc &&
                            sc.MultiPartIdentifier.Identifiers.Select(x=>x.Value).SequenceEqual(oc.MultiPartIdentifier.Identifiers.Select(x=>x.Value),StringComparer.OrdinalIgnoreCase);
                        if(alias || exactColumn || string.Equals(orderText,outputText,StringComparison.OrdinalIgnoreCase))matches.Add(i);
                    }
                    if(matches.Count==1)index=matches[0];
                }
                if(index<0 || index>=outputs.Length)resolved=false;
                keys.Add(index);
            }
            resultContracts.Add(new { producer="select",start_utf16=select.StartOffset,length_utf16=select.FragmentLength,
                conditional,ordered=order is not null,key_indices=keys,resolved });
        }
    }
    // DML OUTPUT returns rows; OUTPUT INTO is a different node and returns none.
    if(kind=="OutputClause")resultContracts.Add(new {producer="output",start_utf16=f.StartOffset,
        length_utf16=f.FragmentLength,conditional=false,ordered=false,key_indices=Array.Empty<int>(),resolved=true});
    if(f is ExecuteStatement execution) {
        object? Property(object? x,string name)=>x?.GetType().GetProperty(name)?.GetValue(x);
        var entity=execution.ExecuteSpecification.ExecutableEntity;
        var reference=Property(Property(entity,"ProcedureReference"),"ProcedureReference");
        var name=Property(reference,"Name") as SchemaObjectName;
        var parameters=(Property(entity,"Parameters") as IEnumerable)?.Cast<object>().ToArray() ?? Array.Empty<object>();
        var literal=parameters.FirstOrDefault() is object ep ? Property(ep,"ParameterValue") as StringLiteral : null;
        bool noResults=false;
        if(name?.BaseIdentifier.Value.Equals("sp_executesql",StringComparison.OrdinalIgnoreCase)==true && literal is not null) {
            var nested=parser.Parse(new StringReader(literal.Value),out var nestedErrors);
            // Literal assignment-only SELECT cannot emit a rowset. Anything
            // else remains unresolved until its own result contract is bound.
            noResults=nestedErrors.Count==0 && nested is TSqlScript script && script.Batches.SelectMany(x=>x.Statements).All(x=>
                x is SelectStatement st && st.QueryExpression is QuerySpecification qs && qs.FromClause is null && qs.TopRowFilter is null && qs.SelectElements.Count>0 && qs.SelectElements.All(e=>e is SelectSetVariable sv && sv.Expression is VariableReference or Literal));
        }
        execContracts.Add(new {start_utf16=f.StartOffset,length_utf16=f.FragmentLength,
            called_parts=name?.Identifiers.Select(x=>x.Value).ToArray(),no_results_proven=noResults,
            literal_start_utf16=literal?.StartOffset,literal_length_utf16=literal?.FragmentLength,
            literal_sql_sha256=literal is null ? null : Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(literal.Value))).ToLowerInvariant()});
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
        if(new[]{"ROW_NUMBER","LAG","LEAD","FIRST_VALUE","LAST_VALUE"}.Contains(fn) || fn=="STRING_AGG" && function.GetType().GetProperty("WithinGroupClause")?.GetValue(function) is null) nondeterministic.Add(fn+"_ORDER_POLICY");
    }
    // AST spans use UTF-16 offsets, explicitly declared; no source literals/errors echoed.
    nodes.Add(new { kind, assignment_variable=kind=="AssignmentSetClause" && f.GetType().GetProperty("Variable")?.GetValue(f) is not null, node_id=seen.Count, parent_id=parent is null ? (int?)null : nodeIds[parent], start_utf16 = f.StartOffset, length_utf16 = f.FragmentLength, line = f.StartLine });
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
        dependencies, exec_contracts=execContracts, result_producers_complete=true, result_contracts=resultContracts, update_joins=updateJoins, nondeterministic_functions=nondeterministic.OrderBy(x=>x).ToArray(),
        dependency_closure="partial; native catalogue closure required" },
    coverage_catalogue = new { schema="tsql-scriptdom-coverage/1", statements, branches, handlers,
        excluded_declarations=excludedDeclarations,
        scope="procedural statements, IF/WHILE edges and CATCH paths; SQL expression branches excluded" }
};
Console.WriteLine(JsonSerializer.Serialize(payload));
return errors.Count == 0 ? 0 : 1;
