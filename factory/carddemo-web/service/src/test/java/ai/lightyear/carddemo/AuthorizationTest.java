package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.Connection;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

class AuthorizationTest {
    @Test void detailKeyUsesTheParentQualifiedPathWithoutMixingAccounts() {
        byte[] parent={1,2,3},businessKey={4,5,6,7,8,9,10,11};
        byte[] path={1,2,3,4,5,6,7,8,9,10,11};
        assertThrows(IllegalArgumentException.class,()->AuthorizationRecords.key(Map.of("ebcdic_key",path,"parent_path_key",new byte[]{9,9,9})));
        assertArrayEquals(businessKey,AuthorizationRecords.key(Map.of("ebcdic_key",path,"parent_path_key",parent)));
        assertThrows(IllegalArgumentException.class,()->AuthorizationRecords.key(Map.of("ebcdic_key",parent,"parent_path_key",parent)));
    }

    private Bindings bindings()throws Exception{Path root=Path.of(System.getProperty("carddemo.root"));return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());}
    private void set(Bindings b,Map<String,Object> row,String field,String text){row.put(b.field("pautdtl1",field).path("column").asText(),Commarea.encode(text));}
    @Test void sourceRenderingPreservesDeclineLookupDateMoneyAndFraudAttributes()throws Exception{
        var b=bindings();var rows=new TypedRecords(b);var row=rows.initialized("pautdtl1");
        set(b,row,"PA-AUTH-ORIG-DATE","261017");set(b,row,"PA-AUTH-ORIG-TIME","123456");set(b,row,"PA-AUTH-RESP-CODE","05");set(b,row,"PA-AUTH-RESP-REASON","3100");
        row.put(b.field("pautdtl1","PA-APPROVED-AMT").path("column").asText(),new java.math.BigDecimal("12.34"));
        set(b,row,"PA-AUTH-FRAUD","F");set(b,row,"PA-FRAUD-RPT-DATE","10/17/26");
        var frame=new ScreenFrame(b,"COPAUS1C");new AuthorizationRendering(b).detail(frame,row);
        assertEquals("10/17/26  ",frame.values.get("AUTHDT"));assertEquals("12:34:56  ",frame.values.get("AUTHTM"));
        assertEquals("D",frame.values.get("AUTHRSP"));assertEquals("RED",frame.attributes.get("AUTHRSP").get("color"));
        assertEquals("3100-INVALID CARD",frame.values.get("AUTHRSN").stripTrailing());assertEquals("F-10/17/26",frame.values.get("AUTHFRD").stripTrailing());
        assertEquals("12.34",frame.values.get("AUTHAMT").strip());assertFalse(frame.trace.isEmpty());
        set(b,row,"PA-AUTH-RESP-REASON","ZZZZ");new AuthorizationRendering(b).detail(frame,row);assertEquals("9999-ERROR",frame.values.get("AUTHRSN").stripTrailing());
    }
    @Test void pf3ExitsBothAuthorizationScreensWithoutDatabaseAccess()throws Exception{
        var b=bindings();Connection db=mock(Connection.class);
        for(String program:List.of("COPAUS0C","COPAUS1C")){
            var area=new Commarea(b.root.path("program_commareas").path(program),null);
            TransactionService service=program.equals("COPAUS0C")?new AuthorizationListService(b):new AuthorizationDetailService(b);
            assertEquals(program.equals("COPAUS0C")?"COMEN01C":"COPAUS0C",service.interact(db,area,"PF3",Map.of()).nextProgram());
        }verifyNoInteractions(db);
    }
    @Test void receivedBlankAccountClearsNonMdtFieldsButRetainsProtectedFset()throws Exception{
        var b=bindings();var prior=new ScreenFrame(b,"COPAUS0C");
        prior.set("CUSTID","123456789");prior.set("ADDR001","OLD ADDRESS");prior.set("APPRCNT","007");
        prior.set("CREDLIM","     6169.00");prior.set("TRNID01","RETAINED");
        var area=new Commarea(b.root.path("program_commareas").path("COPAUS0C"),null);Connection db=mock(Connection.class);
        var service=new AuthorizationListService(b);var result=service.interact(db,area,"ENTER",Map.of(),prior);
        assertEquals(" ".repeat(9),result.screen().values.get("CUSTID"));
        assertEquals(" ".repeat(25),result.screen().values.get("ADDR001"));
        assertEquals("   ",result.screen().values.get("APPRCNT"));
        assertEquals("     6169.00",result.screen().values.get("CREDLIM"));
        assertEquals("RETAINED",result.screen().values.get("TRNID01").stripTrailing());
        assertEquals("Please enter Acct Id...",result.screen().message);verifyNoInteractions(db);
        assertThrows(IllegalArgumentException.class,()->service.interact(db,area,"ENTER",Map.of("CUSTID","OVERRIDE"),prior));
    }
    @Test void topPagePf7DoesNotInventAnAccountCursorAfterReceive()throws Exception{
        var b=bindings();Connection db=mock(Connection.class);var service=new AuthorizationListService(b);
        for(String page:List.of("0","1")){
            var prior=new ScreenFrame(b,"COPAUS0C");prior.cursor="ACCTID";
            var area=new Commarea(b.root.path("program_commareas").path("COPAUS0C"),null);
            area.set("CDEMO-CPVS-PAGE-NUM",page);area.set("CDEMO-CPVS-NEXT-PAGE-FLG","N");
            var result=service.interact(db,area,"PF7",Map.of("ACCTID","00000000050"),prior);
            assertEquals("",result.screen().cursor);
            assertEquals("You are already at the top of the page...",result.screen().message);
            assertEquals("00000000050",result.screen().values.get("ACCTID"));
            var forward=service.interact(db,area,"PF8",Map.of("ACCTID","00000000050"),result.screen());
            assertEquals("ACCTID",forward.screen().cursor);
            assertEquals("You are already at the bottom of the page...",forward.screen().message);
        }
        verifyNoInteractions(db);
    }
    @Test void consecutiveMissingReadStringsRetainThePreviousTail() {
        String buffer=" ".repeat(75);
        buffer=AuthorizationListService.stringOverlay(buffer,"Account:00000000000 not found in XREF file. Resp:000000013 Reas:000000000");
        buffer=AuthorizationListService.stringOverlay(buffer,"Account:00000000000 not found in ACCT file. Resp:000000013 Reas:000000000");
        buffer=AuthorizationListService.stringOverlay(buffer,"Customer:000000000 not found in CUST file. Resp:000000013 Reas:000000000");
        assertEquals("Customer:000000000 not found in CUST file. Resp:000000013 Reas:0000000000",buffer.stripTrailing());
    }
    @Test void rawNullProjectionAndFreshStringStorageDoNotReuseTerminalText()throws Exception{
        var b=bindings();var frame=new ScreenFrame(b,"COPAUS0C");var renderer=new AuthorizationRendering(b);
        frame.set("CNAME","OLDER CUSTOMER");var e=renderer.edits("COPAUS0C",frame);
        e.put("CNAMEO","\u0000SHOULD NOT DISPLAY");assertEquals("OLDER CUSTOMER",frame.values.get("CNAME").stripTrailing());
        e.put("CNAMEO","A\u0000B");assertEquals("A B",frame.values.get("CNAME").stripTrailing());
        var records=new TypedRecords(b);
        renderer.account(frame,Map.of("acctdata",records.initialized("acctdata"),"custdata",records.initialized("custdata")),null);
        assertEquals(" ".repeat(25),frame.values.get("CNAME"));
        assertEquals(","+" ".repeat(24),frame.values.get("ADDR001"));
    }
    @Test void sourceMoneyPictureKeepsMandatoryZeroAndLeadingMinus() {
        assertEquals("        0.00",ScreenProjection.edited("0","-ZZZZZZZ9.99"));
        assertEquals("-      12.34",ScreenProjection.edited("-12.34","-ZZZZZZZ9.99"));
    }
    @Test void detailReconstructionRetainsFillerAndRejectsChangedTypedValueWithoutHash()throws Exception{
        var b=bindings();var mapping=b.mapping("pautdtl1");Commarea area=new Commarea(mapping,null);area.set("PA-AUTH-ORIG-DATE","261017");
        var image=TypedRecordImage.project(mapping,area.bytes());Map<String,Object> row=new LinkedHashMap<>(image.columns());row.put("encoding_meta",image.metadata());row.put("source_sha256",image.sha256());
        assertArrayEquals(area.bytes(),TypedRecordImage.reconstruct(mapping,row));
        set(b,row,"PA-AUTH-FRAUD","F");assertThrows(IllegalArgumentException.class,()->TypedRecordImage.reconstruct(mapping,row));
    }
    @Test void pythonProjectionNullSignDoesNotBecomeAnInvalidZeroNibble()throws Exception{
        var b=bindings();var mapping=b.mapping("pautdtl1");Commarea area=new Commarea(mapping,null);
        area.set("PA-PROCESSING-CODE","123456");area.set("PA-POS-ENTRY-MODE","12");
        var image=TypedRecordImage.project(mapping,area.bytes());
        var mapper=JsonMapper.builder().build();
        var meta=(tools.jackson.databind.node.ObjectNode)mapper.readTree(image.metadata());
        // Match lightyear_mainframe.records._number -> codec.project, not Java's own format.
        for(var f:mapping.path("fields"))if(f.path("digits").asInt()>0 && !f.path("signed").asBoolean() && f.path("usage").asText().equals("DISPLAY")){
            var rep=(tools.jackson.databind.node.ObjectNode)meta.path("representations").path(f.path("path").asText());
            rep.putNull("sign_code");rep.put("negative_zero",false);
        }
        Map<String,Object> row=new LinkedHashMap<>(image.columns());row.put("encoding_meta",mapper.writeValueAsString(meta));row.put("source_sha256",image.sha256());
        assertArrayEquals(area.bytes(),TypedRecordImage.reconstruct(mapping,row));
        // A present invalid sign must still be rejected; this is not relaxed numeric validation.
        var signed=(tools.jackson.databind.node.ObjectNode)meta.path("representations").path(b.field("pautdtl1","PA-AUTH-DATE-9C").path("path").asText());
        signed.put("sign_code",0);row.put("encoding_meta",mapper.writeValueAsString(meta));
        assertEquals("record-sign-code",assertThrows(IllegalArgumentException.class,()->TypedRecordImage.reconstruct(mapping,row)).getMessage());
    }

}
