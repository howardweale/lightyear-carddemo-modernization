package ai.lightyear.carddemo;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

class SourceEditsTest {
    private SourceEdits edits()throws Exception{
        var mapper=JsonMapper.builder().build();Path root=Path.of(System.getProperty("carddemo.root"));
        return new SourceEdits(mapper.readTree(root.resolve("work/carddemo-web-bindings/bindings.json").toFile()).path("account_update").path("generic_edits"));
    }
    private void operand(SourceEdits e,String label,String value,int length){e.put("WS-EDIT-VARIABLE-NAME",label);e.put("WS-EDIT-ALPHANUM-ONLY",value);e.put("WS-EDIT-ALPHANUM-LENGTH",Integer.toString(length));}
    @Test void sourceNumericRejectsBlankNondigitAndZeroButOnlyInspectsSpecifiedWidth()throws Exception{
        for(String value:new String[]{"", "\u0000\u0000\u0000", "12A", "000"}){
            var e=edits();operand(e,"FICO Score",value,3);e.run("1245-EDIT-NUM-REQD");assertTrue(e.condition("INPUT-ERROR"));
            assertFalse(e.condition("FLG-ALPHNANUM-ISVALID"));assertFalse(e.trace().isEmpty());
            assertTrue(e.trace().stream().allMatch(x->x.line()>0&&x.source().equals("app/cbl/COACTUPC.cbl")));
        }
        var e=edits();operand(e,"Zip","12345EXTRA",5);e.run("1245-EDIT-NUM-REQD");assertTrue(e.condition("INPUT-OK"));assertTrue(e.condition("FLG-ALPHNANUM-ISVALID"));
    }
    @Test void firstErrorIsPreservedAcrossEditsAndMessagesUseCobolTruncation()throws Exception{
        var e=edits();operand(e,"First Name","9",25);e.run("1225-EDIT-ALPHA-REQD");String first=e.get("WS-RETURN-MSG");
        assertEquals("First Name can have alphabets only.",first.stripTrailing());
        operand(e,"Zip","00000",5);e.run("1245-EDIT-NUM-REQD");assertEquals(first,e.get("WS-RETURN-MSG"));
        var longLabel=edits();operand(longLabel,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","",25);longLabel.run("1215-EDIT-MANDATORY");
        assertEquals("ABCDEFGHIJKLMNOPQRSTUVWXY must be supplied.",longLabel.get("WS-RETURN-MSG").stripTrailing());
    }
    @Test void optionalAndRequiredNamesAndCaseSensitiveYesNoMatchSource()throws Exception{
        var optional=edits();operand(optional,"Middle Name","",25);optional.run("1235-EDIT-ALPHA-OPT");assertTrue(optional.condition("FLG-ALPHA-ISVALID"));
        var required=edits();operand(required,"First Name","",25);required.run("1225-EDIT-ALPHA-REQD");assertTrue(required.condition("FLG-ALPHA-BLANK"));
        for(String input:new String[]{"Y","N","y","n","0"," "}){
            var e=edits();e.put("WS-EDIT-VARIABLE-NAME","Account Status");e.put("WS-EDIT-YES-NO",input);e.run("1220-EDIT-YESNO");
            assertEquals(input.equals("Y")||input.equals("N"),e.condition("INPUT-OK"));
        }
    }
    @Test void sourceInspectMutatesScratchButDoesNotNormalizeInputOrTreatNulAsSpace()throws Exception{
        var e=edits();operand(e,"First Name","Alice Smith",25);e.run("1225-EDIT-ALPHA-REQD");assertTrue(e.condition("FLG-ALPHA-ISVALID"));
        assertEquals(" ".repeat(256),e.get("WS-EDIT-ALPHANUM-ONLY"));
        var mixed=edits();operand(mixed,"First Name","A\u0000",25);mixed.run("1225-EDIT-ALPHA-REQD");assertTrue(mixed.condition("INPUT-ERROR"));
        assertThrows(IllegalArgumentException.class,()->e.run("1250-EDIT-SIGNED-9V2"));
    }
    @Test void lookupEditsPreservePinnedStateZipAndNumericAliasBoundaries()throws Exception{
        for(String state:new String[]{"CA","ca","ZZ"}){
            var e=edits();e.put("ACUP-NEW-CUST-ADDR-STATE-CD",state);e.run("1270-EDIT-US-STATE-CD");
            assertEquals(state.equals("CA"),e.condition("INPUT-OK"));
        }
        for(int score:new int[]{299,300,850,851}){
            var e=edits();e.put("WS-EDIT-VARIABLE-NAME","FICO Score");
            e.put("ACUP-NEW-CUST-FICO-SCORE-X",Integer.toString(score));e.run("1275-EDIT-FICO-SCORE");
            assertEquals(score>=300&&score<=850,e.condition("INPUT-OK"));
        }
        var alias=edits();alias.put("ACUP-NEW-CUST-FICO-SCORE","7");assertEquals("007",alias.get("ACUP-NEW-CUST-FICO-SCORE-X"));
        alias.put("ACUP-NEW-CUST-FICO-SCORE-X","7X0");assertThrows(IllegalArgumentException.class,()->alias.run("1275-EDIT-FICO-SCORE"));
        for(String zip:new String[]{"94105","10001"}){
            var e=edits();e.put("ACUP-NEW-CUST-ADDR-STATE-CD","CA");e.put("ACUP-NEW-CUST-ADDR-ZIP",zip);
            e.run("1280-EDIT-US-STATE-ZIP-CD");assertEquals(zip.equals("94105"),e.condition("INPUT-OK"));
            if(zip.equals("10001")){assertTrue(e.condition("FLG-STATE-NOT-OK"));assertTrue(e.condition("FLG-ZIPCODE-NOT-OK"));
                assertEquals("Invalid zip code for state",e.get("WS-RETURN-MSG").stripTrailing());}
        }
    }

    @Test void ssnRetainsTheSourceImplicitScopeAndFirstError()throws Exception{
        var valid=edits();valid.put("ACUP-NEW-CUST-SSN-1","123");valid.put("ACUP-NEW-CUST-SSN-2","45");valid.put("ACUP-NEW-CUST-SSN-3","6789");
        valid.run("1265-EDIT-US-SSN");assertTrue(valid.condition("INPUT-OK"));
        for(int part=1;part<=3;part++)assertTrue(valid.condition("FLG-EDIT-US-SSN-PART"+part+"-ISVALID"));
        var first=edits();first.put("ACUP-NEW-CUST-SSN-1","000");first.put("ACUP-NEW-CUST-SSN-2","00");first.put("ACUP-NEW-CUST-SSN-3","0000");
        String before2=first.get("WS-EDIT-US-SSN-PART2-FLGS"),before3=first.get("WS-EDIT-US-SSN-PART3-FLGS");
        first.run("1265-EDIT-US-SSN");assertEquals(before2,first.get("WS-EDIT-US-SSN-PART2-FLGS"));assertEquals(before3,first.get("WS-EDIT-US-SSN-PART3-FLGS"));
        assertEquals("SSN: First 3 chars must not be zero.",first.get("WS-RETURN-MSG").stripTrailing());
        for(String prefix:new String[]{"666","900","999"}){
            var e=edits();e.put("ACUP-NEW-CUST-SSN-1",prefix);e.put("ACUP-NEW-CUST-SSN-2","00");e.put("ACUP-NEW-CUST-SSN-3","0000");e.run("1265-EDIT-US-SSN");
            assertTrue(e.condition("FLG-EDIT-US-SSN-PART1-NOT-OK"));assertTrue(e.condition("FLG-EDIT-US-SSN-PART2-NOT-OK"));assertTrue(e.condition("FLG-EDIT-US-SSN-PART3-NOT-OK"));
            assertEquals("SSN: First 3 chars: should not be 000, 666, or between 900 and 999",e.get("WS-RETURN-MSG").stripTrailing());
        }
    }

}
