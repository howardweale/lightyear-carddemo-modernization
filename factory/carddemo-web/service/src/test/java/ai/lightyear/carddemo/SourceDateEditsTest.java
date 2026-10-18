package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.time.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

class SourceDateEditsTest {
    private SourceEdits edits()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        var model=JsonMapper.builder().build().readTree(root.resolve("work/carddemo-web-bindings/bindings.json").toFile()).path("account_update").path("date_edits");
        return new SourceEdits(model,Clock.fixed(Instant.parse("2026-10-17T12:00:00Z"),ZoneOffset.UTC));
    }
    @Test void sourceDateRangeFallsThroughInternalExitLabelsAndRetainsLeapRules()throws Exception{
        for(String date:new String[]{"19000228","20000229","20240229","20991231"}){
            var e=edits();e.put("WS-EDIT-DATE-CCYYMMDD",date);e.put("WS-EDIT-VARIABLE-NAME","Open Date");e.run("EDIT-DATE-CCYYMMDD");
            assertTrue(e.condition("INPUT-OK"),date);assertTrue(e.condition("WS-EDIT-DATE-IS-VALID"),date);
            assertEquals("0000",e.get("WS-SEVERITY"));assertFalse(e.trace().isEmpty());
            assertTrue(e.trace().stream().allMatch(x->x.line()>0&&x.source().equals("app/cpy/CSUTLDPY.cpy")));
        }
        for(String date:new String[]{"19000229","20230229","20260431","20260230","20261301","20260001","20260100","20260132"}){
            var e=edits();e.put("WS-EDIT-DATE-CCYYMMDD",date);e.put("WS-EDIT-VARIABLE-NAME","Open Date");e.run("EDIT-DATE-CCYYMMDD");
            assertTrue(e.condition("INPUT-ERROR"),date);assertFalse(e.condition("WS-EDIT-DATE-IS-VALID"),date);
            assertFalse(e.get("WS-RETURN-MSG").stripTrailing().isEmpty());
        }
    }
    @Test void sourceBirthDateRejectsTodayAsWellAsFutureAndUsesInjectedClock()throws Exception{
        for(String date:new String[]{"20261016","20261017","20261018"}){
            var e=edits();e.put("WS-EDIT-DATE-CCYYMMDD",date);e.put("WS-EDIT-VARIABLE-NAME","Date of Birth");
            e.run("EDIT-DATE-CCYYMMDD");assertTrue(e.condition("INPUT-OK"));e.run("EDIT-DATE-OF-BIRTH");
            assertEquals(date.equals("20261016"),e.condition("INPUT-OK"));
            if(!date.equals("20261016"))assertEquals("Date of Birth:cannot be in the future",e.get("WS-RETURN-MSG").stripTrailing());
        }
    }
    @Test void copiedGroupAndNumericViewsShareBytes()throws Exception{
        var e=edits();e.put("WS-EDIT-DATE-CCYYMMDD","20000229");
        assertEquals("20",e.get("WS-EDIT-DATE-CC-N"));assertEquals("00",e.get("WS-EDIT-DATE-YY-N"));
        assertEquals("02",e.get("WS-EDIT-DATE-MM-N"));assertEquals("29",e.get("WS-EDIT-DATE-DD-N"));
        e.put("WS-EDIT-DATE-MM-N","12");assertEquals("20001229",e.get("WS-EDIT-DATE-CCYYMMDD"));
    }
}
