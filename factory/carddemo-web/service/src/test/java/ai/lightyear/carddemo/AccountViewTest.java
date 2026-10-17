package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

class AccountViewTest {
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());
    }
    private PreparedStatement statement(Map<String,Object> row)throws Exception {
        PreparedStatement statement=mock(PreparedStatement.class);ResultSet rs=mock(ResultSet.class);when(statement.executeQuery()).thenReturn(rs);
        when(rs.next()).thenReturn(row!=null,false);
        if(row!=null){ResultSetMetaData meta=mock(ResultSetMetaData.class);when(rs.getMetaData()).thenReturn(meta);
            when(meta.getColumnCount()).thenReturn(row.size());int i=0;
            for(var item:row.entrySet()){i++;when(meta.getColumnName(i)).thenReturn(item.getKey());when(rs.getObject(i)).thenReturn(item.getValue());}}
        return statement;
    }
    @Test void accountInvalidAndPf3DoNotAccessDatabase()throws Exception{
        Bindings b=bindings();AccountViewService service=new AccountViewService(b);Connection db=mock(Connection.class);
        for(String value:List.of("","*","00000000000","1234","abcdefghijk")){
            Commarea area=new Commarea(b.root.path("commarea"),null);
            var r=service.interact(db,area,"ENTER",Map.of("ACCTSID",value));
            assertEquals(value.isEmpty()||value.equals("*")?"No input received":"Account Filter must  be a non-zero 11 digit number",r.screen().message);
            assertEquals("00000000000",area.get("CDEMO-ACCT-ID"));assertEquals("ACCTSID",r.screen().cursor);
            assertEquals("RED",r.screen().attributes.get("ACCTSID").get("color"));
        }
        Commarea area=new Commarea(b.root.path("commarea"),null);area.set("CDEMO-FROM-PROGRAM","COMEN01C");area.set("CDEMO-FROM-TRANID","CM00");
        var result=service.interact(db,area,"PF3",Map.of());assertEquals("COMEN01C",result.nextProgram());
        assertEquals("COACTVWC",area.get("CDEMO-FROM-PROGRAM"));assertEquals("CAVW",area.get("CDEMO-FROM-TRANID"));
        assertEquals("0",area.get("CDEMO-PGM-CONTEXT"));verifyNoInteractions(db);
    }
    @Test void alternateNotFoundStopsBeforeMasterReadsAndUsesBoundError()throws Exception{
        Bindings b=bindings();Connection db=mock(Connection.class);PreparedStatement statement=statement(null);
        when(db.prepareStatement(anyString())).thenReturn(statement);
        var r=new AccountViewService(b).interact(db,new Commarea(b.root.path("commarea"),null),"PF7",Map.of("ACCTSID","00000000001"));
        // Unsupported PF7 is ENTER in COACTVWC, not an invented invalid-key error.
        assertEquals(ScreenFrame.pad("Account:00000000001 not found in Cross ref file.  Resp:000000013  Reas:000000000 ",75).stripTrailing(),r.screen().message);
        verify(db,times(1)).prepareStatement(contains("ebcdic_key_aix_"));verify(statement).setBytes(1,Commarea.encode("00000000001"));
    }
    private Map<String,Object> row(Bindings b,String table){Map<String,Object> result=new LinkedHashMap<>();
        for(var f:b.mapping(table).path("fields"))if(!f.path("filler").asBoolean() && f.path("table").asText().equals(table)){
            String column=f.path("column").asText();result.put(column,f.path("digits").asInt()>0?java.math.BigDecimal.ZERO:Commarea.encode(" ".repeat(f.path("length").asInt())));
            if(f.path("date").asBoolean())result.put(column+"_raw","2026-10-17");}
        return result;}
    private void set(Bindings b,String table,Map<String,Object> row,String leaf,Object value){row.put(b.field(table,leaf).path("column").asText(),value);}
    @Test void generatedProjectionFormatsMoneySsnDatesAndNames()throws Exception{
        Bindings b=bindings();Map<String,Object> acct=row(b,"acctdata"),cust=row(b,"custdata");
        set(b,"acctdata",acct,"ACCT-CURR-BAL",new java.math.BigDecimal("-1234567.89"));
        set(b,"custdata",cust,"CUST-SSN",new java.math.BigDecimal("12345678"));
        set(b,"custdata",cust,"CUST-FIRST-NAME",Commarea.encode("Ada                      "));
        ScreenFrame frame=new ScreenFrame(b,"COACTVWC");
        new ScreenProjection(b).apply(frame,b.root.path("account_view_projection"),Map.of("acctdata",acct,"custdata",cust));
        assertEquals("-  1,234,567.89",frame.values.get("ACURBAL"));
        assertEquals("012-34-5678  ",frame.values.get("ACSTSSN"));
        assertEquals("2026-10-17",frame.values.get("ACSTDOB"));assertEquals("Ada                      ",frame.values.get("ACSFNAM"));
        assertThrows(IllegalArgumentException.class,()->ScreenProjection.edited("1","unrecognized"));
    }
}
