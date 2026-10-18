package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

/** Explicit READ-miss contracts complement the real-PostgreSQL happy-path replay. */
class MasterReadFailureTest {
    Bindings bindings()throws Exception{Path root=Path.of(System.getProperty("carddemo.root"));return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());}
    PreparedStatement statement(Map<String,Object> row)throws Exception{
        var q=mock(PreparedStatement.class);var r=mock(ResultSet.class);when(q.executeQuery()).thenReturn(r);when(r.next()).thenReturn(row!=null,false);
        if(row!=null){var meta=mock(ResultSetMetaData.class);when(r.getMetaData()).thenReturn(meta);when(meta.getColumnCount()).thenReturn(row.size());int i=0;
            for(var entry:row.entrySet()){i++;when(meta.getColumnName(i)).thenReturn(entry.getKey());when(r.getObject(i)).thenReturn(entry.getValue());}}
        return q;
    }
    Map<String,Object> cross(Bindings b){var row=new TypedRecords(b).initialized("cardxref");
        for(var entry:Map.of("XREF-ACCT-ID","00000000050","XREF-CUST-ID","123456789","XREF-CARD-NUM","1234567890123456").entrySet()){
            var field=b.field("cardxref",entry.getKey());row.put(field.path("column").asText(),field.path("digits").asInt()>0?new java.math.BigDecimal(entry.getValue()):Commarea.encode(entry.getValue()));}
        return row;
    }
    @Test void missingMastersRetainFirstErrorAndStillReadCustomerAsPinnedSourceDoes()throws Exception{
        var b=bindings();var typed=new TypedRecords(b);
        for(String program:List.of("COACTVWC","COACTUPC"))for(int absent:new int[]{1,2,3}){
            var db=mock(Connection.class);var xref=statement(cross(b));var account=statement((absent&1)!=0?null:typed.initialized("acctdata"));var customer=statement((absent&2)!=0?null:typed.initialized("custdata"));
            when(db.prepareStatement(anyString())).thenReturn(xref,account,customer);
            var area=new Commarea(b.root.path("program_commareas").path(program),null);TransactionService service=program.equals("COACTVWC")?new AccountViewService(b):new AccountUpdateService(b);
            var initial=service.interact(db,area,"INITIAL",Map.of());
            var result=service.interact(db,area,"ENTER",Map.of("ACCTSID","00000000050"),initial.screen());
            String expected=(absent&1)!=0?"Account:00000000050 not found in Acct Master file.Resp:000000013  Reas:000000000 ":"CustId:123456789 not found in customer master.Resp: 000000013  REAS:000000000 ";
            assertEquals(ScreenFrame.pad(expected,75).stripTrailing(),result.screen().message,program+" missing "+absent);
            assertEquals("123456789",area.get("CDEMO-CUST-ID"));assertEquals("1234567890123456",area.get("CDEMO-CARD-NUM"));
            verify(db,times(3)).prepareStatement(anyString());verify(customer).executeQuery();
            verify(db,never()).commit();for(var q:List.of(xref,account,customer))verify(q,never()).executeUpdate();
        }
    }
    @Test void projectionReferenceModificationAcceptsExactEndAndRejectsOutsideStorage()throws Exception{
        var b=bindings();var rows=new TypedRecords(b);var cust=rows.initialized("custdata");cust.put(b.field("custdata","CUST-FIRST-NAME").path("column").asText(),Commarea.encode("ABCDEFGHIJKLMNOPQRSTUVWXY"));
        var json=JsonMapper.builder().build();var projection=new ScreenProjection(b);
        for(int[] shape:new int[][]{{0,25},{24,1},{1,24}}){
            var frame=new ScreenFrame(b,"COACTVWC");var expression=json.valueToTree(List.of(Map.of("operation","string","target","ACSFNAM","pieces",List.of(Map.of("field","CUST-FIRST-NAME","offset",shape[0],"length",shape[1])))));
            projection.apply(frame,expression,Map.of("custdata",cust));
            assertEquals(ScreenFrame.pad("ABCDEFGHIJKLMNOPQRSTUVWXY".substring(shape[0],shape[0]+shape[1]),25),frame.values.get("ACSFNAM"));
        }
        for(int[] shape:new int[][]{{-1,1},{0,0},{24,2}}){
            var frame=new ScreenFrame(b,"COACTVWC");var expression=json.valueToTree(List.of(Map.of("operation","string","target","ACSFNAM","pieces",List.of(Map.of("field","CUST-FIRST-NAME","offset",shape[0],"length",shape[1])))));
            assertThrows(IllegalArgumentException.class,()->projection.apply(frame,expression,Map.of("custdata",cust)));
        }
    }
}
