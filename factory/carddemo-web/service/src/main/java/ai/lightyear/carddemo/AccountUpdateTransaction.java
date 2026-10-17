package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;
import java.util.function.Function;
import tools.jackson.databind.JsonNode;

/** COACTUPC 9500/9600/9700: source-bound saved state and locked two-record rewrite.
 * This component is not exposed until the screen validation/state machine is complete.
 */
public final class AccountUpdateTransaction {
    private final Bindings bindings;private final TypedRecords records;
    public enum Outcome { UPDATED_PENDING_COMMIT, ACCOUNT_NOT_FOUND, CUSTOMER_NOT_FOUND, CONFLICT }
    public AccountUpdateTransaction(Bindings bindings){this.bindings=bindings;records=new TypedRecords(bindings);}
    private String field(String name,Commarea area,Map<String,Map<String,Object>> rows){
        if(name.startsWith("ACUP-")||name.startsWith("CDEMO-"))return area.get(name);
        for(JsonNode mapping:bindings.data.path("mappings"))for(JsonNode f:mapping.path("fields")){
            String path=f.path("path").asText();if(path.substring(path.lastIndexOf('.')+1).equals(name)){
                String table=mapping.path("table").asText();Map<String,Object> row=rows.get(table);
                if(row==null)throw new IllegalArgumentException("update-record-missing");return records.text(table,row,name);
            }
        }throw new IllegalArgumentException("update-expression-field");
    }
    private static String expression(JsonNode e,Function<String,String> fields){
        return e.path("operation").asText().equals("literal")?e.path("value").asText():ChangeDetection.evaluate(e,fields);
    }
    public void capture(Commarea area,Map<String,Map<String,Object>> rows){
        for(JsonNode move:bindings.root.path("account_update").path("fetched"))
            area.set(move.path("target").asText(),expression(move.path("expression"),name->field(name,area,rows)));
    }
    public Map<String,byte[]> prepare(Commarea area,Map<String,Map<String,Object>> current){
        Map<String,Commarea> buffers=new LinkedHashMap<>();
        for(String name:List.of("ACCT-UPDATE-RECORD","CUST-UPDATE-RECORD"))
            buffers.put(name,new Commarea(bindings.root.path("account_update").path("buffers").path(name),null));
        for(JsonNode transfer:bindings.root.path("account_update").path("writes")){
            String target=transfer.path("target").asText();String value;
            if(transfer.path("operation").asText().equals("move"))value=expression(transfer.path("expression"),name->field(name,area,current));
            else if(transfer.path("operation").asText().equals("string")){
                StringBuilder text=new StringBuilder();for(JsonNode piece:transfer.path("pieces"))text.append(expression(piece,name->field(name,area,current)));value=text.toString();
            }else throw new IllegalArgumentException("update-transfer-operation");
            buffers.get(target.startsWith("ACCT-")?"ACCT-UPDATE-RECORD":"CUST-UPDATE-RECORD").set(target,value);
        }
        return Map.of("acctdata",buffers.get("ACCT-UPDATE-RECORD").bytes(),"custdata",buffers.get("CUST-UPDATE-RECORD").bytes());
    }
    public Outcome save(Connection connection,Commarea area)throws SQLException {
        if(connection.getAutoCommit())throw new IllegalArgumentException("interaction-transaction-required");
        if(!area.get("ACUP-CHANGE-ACTION").equals("N"))throw new IllegalArgumentException("source-confirmation-state-required");
        byte[] accountKey=Commarea.encode(area.get("ACUP-NEW-ACCT-ID")),customerKey=Commarea.encode(area.get("CDEMO-CUST-ID"));
        Map<String,Object> account=records.read(connection,"acctdata",accountKey,true);
        if(account==null)return Outcome.ACCOUNT_NOT_FOUND;
        Map<String,Object> customer=records.read(connection,"custdata",customerKey,true);
        if(customer==null)return Outcome.CUSTOMER_NOT_FOUND;
        Map<String,Map<String,Object>> rows=Map.of("acctdata",account,"custdata",customer);
        if(!ChangeDetection.equal(bindings.root.path("account_update_comparisons").path("concurrency"),name->field(name,area,rows)))return Outcome.CONFLICT;
        Map<String,byte[]> buffers=prepare(area,rows);
        // Project both before either SQL mutation. DB errors propagate to the interaction rollback.
        TypedRecordImage.project(bindings.mapping("acctdata"),buffers.get("acctdata"));
        TypedRecordImage.project(bindings.mapping("custdata"),buffers.get("custdata"));
        records.rewrite(connection,"acctdata",accountKey,buffers.get("acctdata"));
        records.rewrite(connection,"custdata",customerKey,buffers.get("custdata"));
        area.set("ACUP-CHANGE-ACTION","C");return Outcome.UPDATED_PENDING_COMMIT;
    }
}
