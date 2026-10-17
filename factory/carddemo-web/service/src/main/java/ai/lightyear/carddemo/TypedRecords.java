package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** All physical columns are compiler outputs; user input is always a parameter. */
public final class TypedRecords {
    private final Bindings bindings;
    public TypedRecords(Bindings bindings){this.bindings=bindings;}
    public Map<String,Object> read(Connection connection,String table,byte[] key,boolean lock)throws SQLException {
        bindings.mapping(table);
        try(PreparedStatement q=connection.prepareStatement("SELECT * FROM "+identifier(table)+" WHERE ebcdic_key=?"+(lock?" FOR UPDATE":""))){
            q.setBytes(1,key);
            try(ResultSet rs=q.executeQuery()){
                if(!rs.next())return null;
                Map<String,Object> row=new LinkedHashMap<>();
                ResultSetMetaData meta=rs.getMetaData();
                for(int i=1;i<=meta.getColumnCount();i++)row.put(meta.getColumnName(i),rs.getObject(i));
                if(rs.next())throw new SQLException("primary-key-not-unique");return row;
            }
        }
    }
    public String text(String table,Map<String,Object> row,String leaf){
        JsonNode f=bindings.field(table,leaf);Object value=row.get(f.path("column").asText()+(f.path("date").asBoolean()?"_raw":""));
        if(value instanceof byte[] bytes)return new String(bytes,Commarea.EBCDIC);
        if(value==null)throw new IllegalArgumentException("required-column-null");
        if(f.path("digits").asInt()>0){
            java.math.BigDecimal number=new java.math.BigDecimal(value.toString());int scale=f.path("scale").asInt();
            String n=number.abs().setScale(scale).toPlainString();int digits=f.path("digits").asInt();
            int width=digits+(scale>0?1:0);n="0".repeat(Math.max(0,width-n.length()))+n;
            return number.signum()<0?"-"+n:n;
        }
        return value.toString();
    }
    public Map<String,Object> readByField(Connection connection,String table,String leaf,byte[] key)throws SQLException {
        JsonNode field=bindings.field(table,leaf),selected=null;
        for(JsonNode candidate:bindings.mapping(table).path("keys"))
            if(candidate.path("key_offset").asInt()==field.path("offset").asInt() && candidate.path("key_length").asInt()==field.path("length").asInt()){
                if(selected!=null)throw new IllegalArgumentException("ambiguous-access-key");selected=candidate;}
        if(selected==null || key.length!=selected.path("key_length").asInt())throw new IllegalArgumentException("source-access-key-unmapped");
        String column=identifier(selected.path("column").asText());
        // A nonunique alternate index returns its first EBCDIC primary key, as READ does.
        try(PreparedStatement q=connection.prepareStatement("SELECT * FROM "+identifier(table)+" WHERE "+column+"=? ORDER BY ebcdic_key LIMIT 1")){
            q.setBytes(1,key);try(ResultSet rs=q.executeQuery()){
                if(!rs.next())return null;Map<String,Object> row=new LinkedHashMap<>();ResultSetMetaData meta=rs.getMetaData();
                for(int i=1;i<=meta.getColumnCount();i++)row.put(meta.getColumnName(i),rs.getObject(i));return row;
            }
        }
    }
    /** Caller owns commit/rollback and acquires both source records before rewriting. */
    public void rewrite(Connection connection,String table,byte[] originalKey,byte[] raw)throws SQLException {
        TypedRecordImage.Image image=TypedRecordImage.project(bindings.mapping(table),raw);
        if(!Arrays.equals(originalKey,(byte[])image.columns().get("ebcdic_key")))throw new IllegalArgumentException("rewrite-primary-key-change");
        List<String> clauses=new ArrayList<>();List<Object> values=new ArrayList<>();
        for(var entry:image.columns().entrySet()){clauses.add(identifier(entry.getKey())+"=?");values.add(entry.getValue());}
        clauses.add("encoding_meta=?::jsonb");values.add(image.metadata());
        clauses.add("source_sha256=?");values.add(image.sha256());values.add(originalKey);
        try(PreparedStatement statement=connection.prepareStatement("UPDATE "+identifier(table)+" SET "+String.join(",",clauses)+" WHERE ebcdic_key=?")){
            for(int i=0;i<values.size();i++)statement.setObject(i+1,values.get(i));
            if(statement.executeUpdate()!=1)throw new SQLException("rewrite-record-not-found");
        }
    }
    public static String identifier(String value){if(!value.matches("[a-z][a-z0-9_]{0,62}"))throw new IllegalArgumentException("unsafe-sql-identifier");return "\""+value+"\"";}
}
