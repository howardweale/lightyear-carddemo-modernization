package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;

/** Supplemental whole-storage oracle. The frozen full-slice workflow separately
 * compares production interactions to the independent raw COBOL interpreter.
 */
class AccountPhoneDateRulesTest {
    private static JsonNode original,production;
    private static final Clock CLOCK=Clock.fixed(Instant.parse("2026-10-21T12:00:00Z"),ZoneOffset.UTC);
    @BeforeAll static void load() throws Exception {
        original=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update").path("validation");
        production=AccountPhoneDateModel.retire(original);
    }
    private static void sameStorage(SourceEdits expected,SourceEdits actual) throws Exception {
        var storage=SourceEdits.class.getDeclaredField("storage");storage.setAccessible(true);
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        assertArrayEquals(((Commarea)storage.get(expected)).bytes(),((Commarea)storage.get(actual)).bytes());
        assertEquals(values.get(expected),values.get(actual));
    }
    private static SourceEdits compare(JsonNode oracle,JsonNode candidate,String paragraph,Map<String,String> input) throws Exception {
        var expected=new SourceEdits(oracle,CLOCK);var actual=new SourceEdits(candidate,CLOCK);
        for(var state:new SourceEdits[]{expected,actual})for(var entry:input.entrySet())state.put(entry.getKey(),entry.getValue());
        RuntimeException expectedFailure=null,actualFailure=null;
        try{expected.run(paragraph);}catch(RuntimeException e){expectedFailure=e;}
        try{actual.run(paragraph);}catch(RuntimeException e){actualFailure=e;}
        if(expectedFailure!=null || actualFailure!=null) {
            assertNotNull(expectedFailure,"candidate-only failure: "+input);
            assertNotNull(actualFailure,"missing source failure: "+input);
            assertEquals(expectedFailure.getClass(),actualFailure.getClass(),input.toString());
        }
        sameStorage(expected,actual);
        return actual;
    }
    private static SourceEdits compare(String paragraph,Map<String,String> input) throws Exception {
        return compare(original,production,paragraph,input);
    }
    private static Map<String,String> phone(String a,String b,String c,String prior) {
        return Map.of("WS-EDIT-US-PHONE-NUMA",a,"WS-EDIT-US-PHONE-NUMB",b,"WS-EDIT-US-PHONE-NUMC",c,
            "WS-RETURN-MSG",prior,"WS-EDIT-VARIABLE-NAME","  Phone  ","WS-US-PHONE-AREA-CODE-TO-EDIT","999");
    }
    @Test void everyAreaCodeUsesOriginalWhitelistAndPreservesScratch() throws Exception {
        for(int a=0;a<1000;a++)compare("1260-EDIT-US-PHONE-NUM",phone(String.format(Locale.ROOT,"%03d",a),"555","0101",""));
    }
    @Test void phoneAllComponentBranchesAndOptionalTypoMatchCompleteStorage() throws Exception {
        for(String a:new String[]{"   ","\0\0\0"," \0 ","A01","000","206","999"})
            for(String b:new String[]{"   ","\0\0\0"," \0 ","B12","000","555"})
                for(String c:new String[]{"    ","\0\0\0\0"," \0  ","C123","0000","0101"})
                    for(String prior:new String[]{"","FIRST ERROR","\0"})compare("1260-EDIT-US-PHONE-NUM",phone(a,b,c,prior));
        var shortcut=compare("1260-EDIT-US-PHONE-NUM",phone("   ","   ","ABCD",""));
        assertTrue(shortcut.condition("WS-EDIT-US-PHONE-IS-VALID"));
        assertEquals("999",shortcut.get("WS-US-PHONE-AREA-CODE-TO-EDIT"));
        var input=new HashMap<>(phone("000","000","0000",""));input.put("WS-EDIT-VARIABLE-NAME","\tPhone\t");
        compare("1260-EDIT-US-PHONE-NUM",input);
    }
    @Test void dateComponentsFallThroughAndRetainAllScratch() throws Exception {
        for(String year:new String[]{"1900","2000","2023","2024","2099","2100","0000","    ","\0\0\0\0","ABCD"})
            for(String month:new String[]{"00","01","02","04","12","13","  ","\0\0","A1","+1","1 "})
                for(String day:new String[]{"00","01","28","29","30","31","32","  ","\0\0","A1","+1","-1","1.","1 "}) {
                    var input=new HashMap<String,String>();input.put("WS-EDIT-DATE-CCYYMMDD",year+month+day);
                    input.put("WS-EDIT-VARIABLE-NAME"," Open Date ");input.put("WS-DIV-BY","7");
                    input.put("WS-DIVIDEND","9");input.put("WS-REMAINDER","3");
                    compare("EDIT-DATE-CCYYMMDD",input);
                }
    }
    @Test void datesPreserveExistingErrorFlagsAndFeedbackStorage() throws Exception {
        for(String date:new String[]{"19000229","20000229","20260431","20261021","        ","2026A132"})
            for(String prior:new String[]{"","FIRST ERROR","\0"})
                for(String inputFlag:new String[]{"0","1","\0"}) {
                    var input=new HashMap<String,String>();input.put("WS-EDIT-DATE-CCYYMMDD",date);
                    input.put("WS-RETURN-MSG",prior);input.put("WS-INPUT-FLAG",inputFlag);
                    input.put("WS-DATE-VALIDATION-RESULT","X".repeat(20));
                    compare("EDIT-DATE-CCYYMMDD",input);
                }
    }
    @Test void nonzeroLeFeedbackStillFallsThroughFinalValidityAssignment() throws Exception {
        ObjectNode changed=(ObjectNode)original.deepCopy();
        ObjectNode feedback=(ObjectNode)changed.path("service").path("feedback").path("FC-INVALID-DATE");
        feedback.put("severity",4);feedback.put("message",7);
        var result=compare(changed,AccountPhoneDateModel.retire(changed),"EDIT-DATE-CCYYMMDD",
            Map.of("WS-EDIT-DATE-CCYYMMDD","20000229","WS-EDIT-VARIABLE-NAME","Date"));
        assertTrue(result.condition("INPUT-ERROR"));assertTrue(result.condition("WS-EDIT-DATE-IS-VALID"));
        assertEquals("0004",result.get("WS-SEVERITY"));assertEquals("0007",result.get("WS-MSG-NO"));
        assertEquals("Date validation error Sev code: 0004 Message code: 0007",result.get("WS-RETURN-MSG").stripTrailing());
    }
    @Test void birthYesterdayTodayTomorrowAndFarBoundsUsePinnedClock() throws Exception {
        for(String date:new String[]{"19000101","20000229","20261020","20261021","20261022","20991231"})
            for(String prior:new String[]{"","FIRST ERROR","\0"}) {
                var result=compare("EDIT-DATE-OF-BIRTH",Map.of("WS-EDIT-DATE-CCYYMMDD",date,"WS-RETURN-MSG",prior));
                assertEquals(date.compareTo("20261021")>=0,result.condition("INPUT-ERROR"));
                assertEquals("20261021",result.get("WS-CURRENT-DATE-YYYYMMDD"));
            }
    }
    @Test void retirementCopiesOnlyThreeBodiesAndFailsClosedOnMissingBodies() {
        assertNotSame(original,production);
        for(var rule:AccountPhoneDateModel.RULES.entrySet()) {
            assertTrue(original.path("paragraphs").has(rule.getKey()));
            assertFalse(production.path("paragraphs").has(rule.getKey()));
            assertEquals(rule.getValue(),production.path("native_paragraphs").path(rule.getKey()).asText());
            for(String defect:Set.of("missing","empty","scalar","already-native")) {
                ObjectNode invalid=(ObjectNode)original.deepCopy();ObjectNode paragraphs=(ObjectNode)invalid.path("paragraphs");
                switch(defect) {
                    case "missing"->paragraphs.remove(rule.getKey());
                    case "empty"->paragraphs.putArray(rule.getKey());
                    case "scalar"->paragraphs.put(rule.getKey(),"bad");
                    case "already-native"->((ObjectNode)invalid.path("native_paragraphs")).put(rule.getKey(),rule.getValue());
                    default->throw new AssertionError();
                }
                assertThrows(IllegalArgumentException.class,()->AccountPhoneDateModel.retire(invalid));
            }
        }
        for(var entry:original.properties())if(!Set.of("paragraphs","native_paragraphs").contains(entry.getKey()))
            assertEquals(entry.getValue(),production.path(entry.getKey()));
        for(var entry:original.path("paragraphs").properties())if(!AccountPhoneDateModel.RULES.containsKey(entry.getKey()))
            assertEquals(entry.getValue(),production.path("paragraphs").path(entry.getKey()));
    }
    @Test void wholeStorageOracleDetectsByteAndScalarChanges() throws Exception {
        var expected=new SourceEdits(original,CLOCK);var actual=new SourceEdits(original,CLOCK);sameStorage(expected,actual);
        actual.put("WS-EDIT-DATE-CCYYMMDD","20000229");assertThrows(AssertionError.class,()->sameStorage(expected,actual));
        expected.put("WS-EDIT-DATE-CCYYMMDD","20000229");sameStorage(expected,actual);
        actual.put("WS-RETURN-MSG","different");assertThrows(AssertionError.class,()->sameStorage(expected,actual));
    }
}
