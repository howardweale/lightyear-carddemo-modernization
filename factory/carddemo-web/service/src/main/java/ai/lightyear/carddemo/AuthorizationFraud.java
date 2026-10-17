package ai.lightyear.carddemo;

import java.sql.*;
import java.time.*;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** COPAUS2C LINK and COPAUS1C REPL share the caller's database transaction. */
public final class AuthorizationFraud {
    private final Bindings b;private final TypedRecords records;private final Clock clock;
    public AuthorizationFraud(Bindings b){this(b,Clock.systemUTC());}
    public AuthorizationFraud(Bindings b,Clock clock){this.b=b;this.clock=clock;records=new TypedRecords(b);}
    public Map<String,Object> apply(Connection db,Commarea area,Map<String,Object> detail)throws SQLException{
        if(db.getAutoCommit())throw new IllegalArgumentException("fraud-transaction-required");
        JsonNode mapping=b.mapping("pautdtl1");Commarea image=new Commarea(mapping,TypedRecordImage.reconstruct(mapping,detail));
        String action=image.get("PA-AUTH-FRAUD").equals("F")?"R":"F";
        image.set("PA-AUTH-FRAUD",action);
        LocalDate today=LocalDate.now(clock);image.set("PA-FRAUD-RPT-DATE",today.format(java.time.format.DateTimeFormatter.ofPattern("MM/dd/yy",Locale.ROOT)));
        JsonNode schema=b.root.path("fraud");List<String> columns=new ArrayList<>(),parameters=new ArrayList<>();List<Object> values=new ArrayList<>();
        for(JsonNode binding:schema.path("action").path("bindings")){
            String column=binding.path("column").asText();JsonNode expression=binding.path("expression");Object value;
            switch(expression.path("kind").asText()){
                case "current-date":value=java.sql.Date.valueOf(today);break;
                case "authorization-time":{
                    String date=image.get(expression.path("date_field").asText());
                    long reverse=Long.parseLong(image.get(expression.path("time_field").asText()));
                    String time=String.format(Locale.ROOT,"%09d",expression.path("complement").asLong()-reverse);
                    // Explicit public-reference year window, recorded in generated limitations.
                    LocalDate day=LocalDate.of(2000+Integer.parseInt(date.substring(0,2)),Integer.parseInt(date.substring(2,4)),Integer.parseInt(date.substring(4,6)));
                    value=Timestamp.valueOf(day.atTime(Integer.parseInt(time.substring(0,2)),Integer.parseInt(time.substring(2,4)),Integer.parseInt(time.substring(4,6)),Integer.parseInt(time.substring(6,9))*1000000));break;}
                case "field":{
                    String source=expression.path("field").asText();String text=switch(source){case "WS-ACCT-ID"->area.get("CDEMO-ACCT-ID");case "WS-CUST-ID"->area.get("CDEMO-CUST-ID");case "WS-FRD-ACTION"->action;default->image.get(source);};
                    JsonNode definition=null;for(JsonNode f:schema.path("fields"))if(f.path("name").asText().equals(column))definition=f;
                    if(definition==null)throw new IllegalArgumentException("fraud-column-unmapped");String type=definition.path("sql_type").asText();
                    value=type.startsWith("decimal")||type.equals("smallint")?new java.math.BigDecimal(text):text;break;}
                default:throw new IllegalArgumentException("fraud-expression");
            }
            columns.add(TypedRecords.identifier(column));parameters.add("?");values.add(value);
        }
        List<String> keys=new ArrayList<>(),updates=new ArrayList<>();for(JsonNode key:schema.path("primary_key"))keys.add(TypedRecords.identifier(key.asText()));
        for(JsonNode column:schema.path("action").path("update_columns")){String id=TypedRecords.identifier(column.asText());updates.add(id+"=EXCLUDED."+id);}
        String sql="INSERT INTO "+TypedRecords.identifier(schema.path("table").asText())+" ("+String.join(",",columns)+") VALUES ("+String.join(",",parameters)+") ON CONFLICT ("+String.join(",",keys)+") DO UPDATE SET "+String.join(",",updates);
        try(var statement=db.prepareStatement(sql)){for(int i=0;i<values.size();i++)statement.setObject(i+1,values.get(i));if(statement.executeUpdate()!=1)throw new SQLException("fraud-action-row-count");}
        byte[] raw=image.bytes();records.rewrite(db,"pautdtl1",AuthorizationRecords.key(detail),raw);
        var projected=TypedRecordImage.project(mapping,raw);Map<String,Object> result=new LinkedHashMap<>(detail);result.putAll(projected.columns());result.put("encoding_meta",projected.metadata());result.put("source_sha256",projected.sha256());return result;
    }
}
