package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.*;
import java.math.BigDecimal;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

class AccountUpdateTransactionTest {
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());
    }
    private Commarea accountBuffer(Bindings b){
        Commarea buffer=new Commarea(b.root.path("account_update").path("buffers").path("ACCT-UPDATE-RECORD"),null);
        buffer.set("ACCT-UPDATE-ID","123");buffer.set("ACCT-UPDATE-GROUP-ID","GROUP1");buffer.set("ACCT-UPDATE-CURR-BAL","-12.34");
        for(String name:List.of("ACCT-UPDATE-OPEN-DATE","ACCT-UPDATE-EXPIRAION-DATE","ACCT-UPDATE-REISSUE-DATE"))buffer.set(name,"2026-10-17");
        return buffer;
    }
    @Test void sourceRewriteLayoutIsAppliedByBytesIncludingTheZipGroupDiscrepancy()throws Exception{
        Bindings b=bindings();byte[] raw=accountBuffer(b).bytes();
        var image=TypedRecordImage.project(b.mapping("acctdata"),raw);
        assertEquals(300,raw.length);
        assertArrayEquals(Commarea.encode("GROUP1    "),(byte[])image.columns().get(b.field("acctdata","ACCT-ADDR-ZIP").path("column").asText()));
        assertArrayEquals(Commarea.encode("          "),(byte[])image.columns().get(b.field("acctdata","ACCT-GROUP-ID").path("column").asText()));
        assertEquals(new BigDecimal("-12.34"),image.columns().get(b.field("acctdata","ACCT-CURR-BAL").path("column").asText()));
        var metadata=JsonMapper.builder().build().readTree(image.metadata());
        assertEquals(300,metadata.path("length").asInt());assertFalse(metadata.path("filler").isEmpty());
        assertFalse(image.columns().containsKey("raw_record"));
    }
    @Test void invalidDateOrChangedPrimaryKeyRefusesBeforeAnySqlMutation()throws Exception{
        Bindings b=bindings();Commarea buffer=accountBuffer(b);buffer.set("ACCT-UPDATE-OPEN-DATE","2026-02-30");
        assertThrows(java.time.DateTimeException.class,()->TypedRecordImage.project(b.mapping("acctdata"),buffer.bytes()));
        Connection db=mock(Connection.class);
        assertThrows(IllegalArgumentException.class,()->new TypedRecords(b).rewrite(db,"acctdata",Commarea.encode("00000000999"),accountBuffer(b).bytes()));
        verifyNoInteractions(db);
    }
    private Map<String,Object> row(Bindings b,String table){
        Map<String,Object> row=new LinkedHashMap<>();
        for(var f:b.mapping(table).path("fields"))if(!f.path("filler").asBoolean()){
            String column=f.path("column").asText();
            row.put(column,f.path("digits").asInt()>0?BigDecimal.ZERO:Commarea.encode(" ".repeat(f.path("length").asInt())));
            if(f.path("date").asBoolean())row.put(column+"_raw","2026-10-17");
        }return row;
    }
    private PreparedStatement statement(Map<String,Object> row)throws Exception{
        PreparedStatement q=mock(PreparedStatement.class);ResultSet rs=mock(ResultSet.class);ResultSetMetaData meta=mock(ResultSetMetaData.class);
        when(q.executeQuery()).thenReturn(rs);when(rs.next()).thenReturn(true,false);when(rs.getMetaData()).thenReturn(meta);when(meta.getColumnCount()).thenReturn(row.size());
        int i=0;for(var entry:row.entrySet()){i++;when(meta.getColumnName(i)).thenReturn(entry.getKey());when(rs.getObject(i)).thenReturn(entry.getValue());}return q;
    }
    @Test void concurrencyCheckLocksBothRecordsAndNeverWritesOnConflict()throws Exception{
        Bindings b=bindings();AccountUpdateTransaction update=new AccountUpdateTransaction(b);
        var account=row(b,"acctdata");var customer=row(b,"custdata");var cross=row(b,"cardxref");
        Commarea area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        update.capture(area,Map.of("acctdata",account,"custdata",customer,"cardxref",cross));
        area.set("ACUP-NEW-ACCT-ID","0");area.set("ACUP-CHANGE-ACTION","N");
        // A concurrent name edit must not be lost even when only another field is submitted.
        customer.put(b.field("custdata","CUST-FIRST-NAME").path("column").asText(),Commarea.encode("Changed                  "));
        Connection db=mock(Connection.class);when(db.getAutoCommit()).thenReturn(false);
        when(db.prepareStatement(startsWith("SELECT * FROM \"acctdata\""))).thenReturn(statement(account));
        when(db.prepareStatement(startsWith("SELECT * FROM \"custdata\""))).thenReturn(statement(customer));
        assertEquals(AccountUpdateTransaction.Outcome.CONFLICT,update.save(db,area));
        verify(db,times(2)).prepareStatement(endsWith("FOR UPDATE"));
        verify(db,never()).prepareStatement(startsWith("UPDATE"));verify(db,never()).commit();
    }
    @Test void confirmationAndTransactionAreBothRequired()throws Exception{
        Bindings b=bindings();Commarea area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        Connection db=mock(Connection.class);when(db.getAutoCommit()).thenReturn(true);
        assertThrows(IllegalArgumentException.class,()->new AccountUpdateTransaction(b).save(db,area));
        when(db.getAutoCommit()).thenReturn(false);
        assertThrows(IllegalArgumentException.class,()->new AccountUpdateTransaction(b).save(db,area));
        verify(db,never()).prepareStatement(anyString());
    }
}
