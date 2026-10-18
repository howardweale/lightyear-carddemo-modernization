package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** GU/GNP equivalents for the two source DBD segments; no IMS execution. */
public final class AuthorizationRecords {
    private final Bindings b;private final TypedRecords records;
    public AuthorizationRecords(Bindings bindings){b=bindings;records=new TypedRecords(b);}
    private static Map<String,Object> row(ResultSet rs)throws SQLException{
        Map<String,Object> result=new LinkedHashMap<>();var meta=rs.getMetaData();
        for(int i=1;i<=meta.getColumnCount();i++)result.put(meta.getColumnName(i),rs.getObject(i));return result;
    }
    public Map<String,Object> summary(Connection db,String account)throws SQLException{
        String column=TypedRecords.identifier(b.field("pautsum0","PA-ACCT-ID").path("column").asText());
        try(var q=db.prepareStatement("SELECT * FROM pautsum0 WHERE "+column+"=?")){
            q.setBigDecimal(1,new java.math.BigDecimal(account));try(var rs=q.executeQuery()){
                if(!rs.next())return null;var result=row(rs);if(rs.next())throw new SQLException("summary-key-not-unique");return result;}
        }
    }
    public List<Map<String,Object>> page(Connection db,Map<String,Object> parent,byte[] start,boolean inclusive,int limit)throws SQLException{
        if(limit<1||limit>6)throw new IllegalArgumentException("authorization-page-limit");
        if(parent==null)return List.of();
        // DBPAUTP0 declares PAUT9CTS as SEQ,U (TYPE=C). GNP follows its
        // ascending byte key within the established parent, not import ordinal.
        String sql="SELECT * FROM pautdtl1 WHERE parent_path_key=?"+(start==null?"":" AND (ebcdic_key,path_key)"+(inclusive?">=":">")+"(SELECT ebcdic_key,path_key FROM pautdtl1 WHERE parent_path_key=? AND ebcdic_key=?)")+" ORDER BY ebcdic_key,path_key LIMIT ?";
        try(var q=db.prepareStatement(sql)){int i=1;q.setBytes(i++,(byte[])parent.get("path_key"));if(start!=null){q.setBytes(i++,(byte[])parent.get("path_key"));q.setBytes(i++,path(parent,start));}q.setInt(i,limit);
            try(var rs=q.executeQuery()){List<Map<String,Object>> rows=new ArrayList<>();while(rs.next())rows.add(row(rs));return rows;}}
    }
    public Map<String,Object> detail(Connection db,Map<String,Object> parent,byte[] key,boolean lock)throws SQLException{
        if(parent==null)return null;
        try(var q=db.prepareStatement("SELECT * FROM pautdtl1 WHERE parent_path_key=? AND ebcdic_key=?"+(lock?" FOR UPDATE":""))){
            q.setBytes(1,(byte[])parent.get("path_key"));q.setBytes(2,path(parent,key));try(var rs=q.executeQuery()){if(!rs.next())return null;return row(rs);}}
    }
    public void load(SourceEdits edits,JsonNode model,String table,Map<String,Object> row){
        if(row==null)return;
        for(JsonNode f:b.mapping(table).path("fields")){
            String name=f.path("path").asText();name=name.substring(name.lastIndexOf('.')+1);
            if(!f.path("filler").asBoolean()&&model.path("fields").has(name))edits.put(name,records.text(table,row,name));
        }
    }
    private static byte[] path(Map<String,Object> parent,byte[] key){byte[] root=(byte[])parent.get("path_key");byte[] result=Arrays.copyOf(root,root.length+key.length);System.arraycopy(key,0,result,root.length,key.length);return result;}
    public static byte[] key(Map<String,Object> row){byte[] path=(byte[])row.get("ebcdic_key"),parent=(byte[])row.get("parent_path_key");if(parent==null||path.length<=parent.length||!Arrays.equals(parent,Arrays.copyOf(path,parent.length)))throw new IllegalArgumentException("detail-path-key");return Arrays.copyOfRange(path,parent.length,path.length);}
}
