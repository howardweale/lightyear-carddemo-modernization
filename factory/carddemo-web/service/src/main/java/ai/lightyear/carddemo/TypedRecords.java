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
        JsonNode f=bindings.field(table,leaf);Object value=row.get(f.path("column").asText());
        if(value instanceof byte[] bytes)return new String(bytes,Commarea.EBCDIC);
        if(value==null)throw new IllegalArgumentException("required-column-null");
        return value.toString();
    }
    public static String identifier(String value){if(!value.matches("[a-z][a-z0-9_]{0,62}"))throw new IllegalArgumentException("unsafe-sql-identifier");return "\""+value+"\"";}
}
