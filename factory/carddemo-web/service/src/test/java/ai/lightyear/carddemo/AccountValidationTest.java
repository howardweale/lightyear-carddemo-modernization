package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.time.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

class AccountValidationTest {
    private final JsonMapper mapper=JsonMapper.builder().build();
    private final Clock clock=Clock.fixed(Instant.parse("2026-10-17T12:00:00Z"),ZoneOffset.UTC);
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),mapper);
    }
    @Test void absentSearchStopsBeforeNonKeyValidationAndPreservesSourceMessage()throws Exception{
        var b=bindings();var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        var edit=new SourceEdits(b.root.path("account_update").path("validation"),clock);
        edit.loadArea(area);edit.put("CC-ACCT-ID","");edit.run("1200-EDIT-MAP-INPUTS");edit.saveArea(area);
        assertTrue(edit.condition("INPUT-ERROR"));assertEquals("No input received",edit.get("WS-RETURN-MSG").stripTrailing());
        assertEquals("00000000000",area.get("ACUP-NEW-ACCT-ID"));
        assertFalse(edit.trace().stream().anyMatch(x->x.source().endsWith("CSUTLDPY.cpy")));
    }
    @Test void unchangedFieldsSkipEveryUnrelatedValidatorAsSourceRequires()throws Exception{
        var b=bindings();var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        area.set("ACUP-CHANGE-ACTION","S");
        var edit=new SourceEdits(b.root.path("account_update").path("validation"),clock);edit.loadArea(area);
        edit.run("1200-EDIT-MAP-INPUTS");edit.saveArea(area);
        assertTrue(edit.condition("INPUT-OK"));assertTrue(edit.condition("NO-CHANGES-FOUND"));
        assertEquals("No change detected with respect to values fetched.",edit.get("WS-RETURN-MSG").stripTrailing());
        assertEquals("S",area.get("ACUP-CHANGE-ACTION"));
        assertFalse(edit.trace().stream().anyMatch(x->x.source().endsWith("CSUTLDPY.cpy")));
    }
    @Test void sourceAttributesAndCursorFollowTheCurrentEditState()throws Exception{
        var b=bindings();var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        var edit=new SourceEdits(b.root.path("account_update").path("validation"),clock);edit.loadArea(area);
        var frame=new ScreenFrame(b,"COACTUPC",clock);edit.attachScreen(frame);
        edit.setCondition("ACUP-DETAILS-NOT-FETCHED");edit.run("3300-SETUP-SCREEN-ATTRS");
        assertEquals(false,frame.attributes.get("ACCTSID").get("protected"));
        assertEquals(true,frame.attributes.get("ACSFNAM").get("protected"));
        edit.setCondition("ACUP-SHOW-DETAILS");edit.setCondition("FOUND-ACCOUNT-DATA");
        edit.run("3300-SETUP-SCREEN-ATTRS");
        assertEquals("ACSTTUS",frame.cursor);assertEquals(false,frame.attributes.get("ACSFNAM").get("protected"));
        assertEquals(true,frame.attributes.get("ACSCTRY").get("protected"));
        assertEquals(true,frame.attributes.get("ACSCTRY").get("modified"));
        edit.setCondition("ACUP-CHANGES-OK-NOT-CONFIRMED");edit.run("3300-SETUP-SCREEN-ATTRS");
        assertEquals(true,frame.attributes.get("ACSFNAM").get("protected"));
        assertThrows(IllegalArgumentException.class,()->edit.receiveScreen(java.util.Map.of("ACSFNAM","tampered")));
    }
}
