package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
import tools.jackson.databind.json.JsonMapper;
import static ai.lightyear.carddemo.AccountTextRules.Status.*;
import static org.junit.jupiter.api.Assertions.*;

class AccountSsnFicoRulesTest {
    private static JsonNode model,original;
    @BeforeAll static void load() throws Exception {
        model=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
        // Supplemental CI oracle: identical storage with original statement bodies.
        ObjectNode copy=(ObjectNode)model.path("validation").deepCopy();
        copy.remove("native_paragraphs");
        ObjectNode paragraphs=(ObjectNode)copy.path("paragraphs");
        for(var item:model.path("generic_edits").path("paragraphs").properties())
            paragraphs.set(item.getKey(),item.getValue());
        original=copy;
    }
    @Test void allThreeDigitSsnPrefixesAndFicoScores() {
        for(int n=0;n<=999;n++) {
            String text=String.format(Locale.ROOT,"%03d",n);
            var result=AccountSsnRule.validate(text,"01","0001");
            assertEquals(text,result.first().input());
            assertEquals(n==0?ZERO:VALID,result.first().status());
            assertEquals(n==666||n>=900,result.restrictedFirst());
            assertEquals(n==0?0:2,result.remaining().size());
            if(n!=0) {
                assertEquals("01",result.remaining().get(0).input());
                assertEquals("0001",result.remaining().get(1).input());
                assertEquals(VALID,result.remaining().get(0).status());
                assertEquals(VALID,result.remaining().get(1).status());
            }
            assertEquals(n>=300&&n<=850,AccountFicoRule.validScore(n));
            assertEquals(n>=300&&n<=850,AccountFicoRule.validDisplay(text));
        }
        assertFalse(AccountFicoRule.validScore(-1));assertFalse(AccountFicoRule.validScore(1000));
    }
    @Test void displayBoundsUseOneInclusiveEbcdicComparison() {
        for(String value:new String[]{"300","301","849","850","4A0","8A0"})
            assertTrue(AccountFicoRule.validDisplay(value),value);
        for(String value:new String[]{"299","851","3A0","9A0"})
            assertFalse(AccountFicoRule.validDisplay(value),value);
        // The storage oracle independently executes the original COBOL statements.
        for(String value:new String[]{"299","300","301","849","850","851","3A0","4A0","8A0","9A0"})
            compare("1275-EDIT-FICO-SCORE",Map.of("ACUP-NEW-CUST-FICO-SCORE-X",value),"");
        assertThrows(IllegalArgumentException.class,()->AccountFicoRule.validDisplay("\u20ac00"));
    }
    @Test void invalidFirstSkipsFollowingPartsButRestrictedFirstDoesNot() {
        for(String first:new String[]{"000","   ","\0\0\0","a01","1 2","\0  "}) {
            var result=AccountSsnRule.validate(first,"00","0000");
            assertEquals(first.equals("000")?ZERO:first.equals("   ")||first.equals("\0\0\0")?MISSING:INVALID,result.first().status());
            assertTrue(result.remaining().isEmpty());assertFalse(result.restrictedFirst());
        }
        for(String first:new String[]{"123","666","900","999"}) {
            var result=AccountSsnRule.validate(first,"00","0000");
            assertEquals(ZERO,result.remaining().get(0).status());
            assertEquals(ZERO,result.remaining().get(1).status());
            var missing=AccountSsnRule.validate(first,"  ","\0\0\0\0");
            assertEquals(MISSING,missing.remaining().get(0).status());
            assertEquals(MISSING,missing.remaining().get(1).status());
            var invalid=AccountSsnRule.validate(first,"A1","1 23");
            assertEquals(INVALID,invalid.remaining().get(0).status());
            assertEquals(INVALID,invalid.remaining().get(1).status());
        }
    }
    @Test void invalidDisplayKeepsDisclosedEbcdicBound() {
        for(String text:new String[]{"4A0","8A0","8Z9","849"})assertTrue(AccountFicoRule.validDisplay(text),text);
        for(String text:new String[]{"3A0","9A0","\0\0\0","   ","A00","299","851"})
            assertFalse(AccountFicoRule.validDisplay(text),text);
    }
    private SourceEdits compare(String paragraph,Map<String,String> values,String prior) {
        var oracle=new SourceEdits(original);var candidate=new SourceEdits(model.path("validation"));
        for(var edits:new SourceEdits[]{oracle,candidate}) {
            edits.put("WS-RETURN-MSG",prior);
            edits.put("WS-EDIT-US-SSN-PART1-FLGS","B");
            edits.put("WS-EDIT-US-SSN-PART2-FLGS","0");
            edits.put("WS-EDIT-US-SSN-PART3-FLGS","B");
            edits.put("WS-EDIT-US-SSN-PART1","777");
            edits.put("WS-EDIT-VARIABLE-NAME","  FICO Score  ");
            edits.put("WS-EDIT-FICO-SCORE-FLGS","B");
            edits.put("WS-EDIT-ALPHANUM-ONLY","STALE SCRATCH");
            for(var item:values.entrySet())edits.put(item.getKey(),item.getValue());
            edits.run(paragraph);
        }
        assertCompleteStorage(oracle,candidate,paragraph+" "+values);
        assertEquals(oracle.condition("INPUT-ERROR"),candidate.condition("INPUT-ERROR"));
        assertFalse(candidate.trace().isEmpty());
        return candidate;
    }
    private static void assertCompleteStorage(SourceEdits oracle,SourceEdits candidate,String context) {
        // Numeric REDEFINES may intentionally contain invalid DISPLAY bytes.
        // Compare every stored byte and every non-storage value without decoding.
        // Reflection keeps this supplemental CI oracle out of production APIs.
        try {
            var storage=SourceEdits.class.getDeclaredField("storage");
            var values=SourceEdits.class.getDeclaredField("values");
            storage.setAccessible(true);values.setAccessible(true);
            var expected=(Commarea)storage.get(oracle);
            var actual=(Commarea)storage.get(candidate);
            assertNotNull(expected);assertNotNull(actual);
            assertArrayEquals(expected.bytes(),actual.bytes(),context);
            assertEquals(values.get(oracle),values.get(candidate),context);
        } catch(ReflectiveOperationException failure) {
            throw new AssertionError("complete storage oracle unavailable",failure);
        }
    }
    @Test void completeStorageComparisonRejectsChangedBytesAndScratchValues() throws Exception {
        var oracle=new SourceEdits(original);var candidate=new SourceEdits(model.path("validation"));
        assertCompleteStorage(oracle,candidate,"initial storage");
        var storage=SourceEdits.class.getDeclaredField("storage");storage.setAccessible(true);
        var actual=(Commarea)storage.get(candidate);byte saved=actual.bytes()[0];
        actual.copyBytes(0,new byte[]{(byte)(saved ^ 1)});
        assertThrows(AssertionError.class,()->assertCompleteStorage(oracle,candidate,"changed byte"));
        actual.copyBytes(0,new byte[]{saved});
        assertCompleteStorage(oracle,candidate,"restored storage");
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        @SuppressWarnings("unchecked") var scratch=(Map<String,String>)values.get(candidate);
        scratch.put("fixture-only-mismatch","different");
        assertThrows(AssertionError.class,()->assertCompleteStorage(oracle,candidate,"changed scratch"));
    }
    private Map<String,String> ssn(String first,String second,String third) {
        return Map.of("ACUP-NEW-CUST-SSN-1",first,"ACUP-NEW-CUST-SSN-2",second,"ACUP-NEW-CUST-SSN-3",third);
    }
    @Test void fullStorageOraclePreservesSsnScopeFirstErrorAndScratch() {
        for(String prior:new String[]{"","FIRST ERROR","\0"})
            for(String first:new String[]{"000","   ","\0\0\0","1A2","123","666","899","900","999"})
                for(String[] rest:new String[][]{{"01","0001"},{"00","0000"},{"  ","\0\0\0\0"},{"A1","1 23"}})
                    compare("1265-EDIT-US-SSN",ssn(first,rest[0],rest[1]),prior);
        var skipped=compare("1265-EDIT-US-SSN",ssn("000","01","0001"),"");
        assertEquals("0",skipped.get("WS-EDIT-US-SSN-PART2-FLGS"));
        assertEquals("B",skipped.get("WS-EDIT-US-SSN-PART3-FLGS"));
        assertEquals("777",skipped.get("WS-EDIT-US-SSN-PART1"));
        assertEquals("SSN: First 3 chars must not be zero.",skipped.get("WS-RETURN-MSG").stripTrailing());
        var restricted=compare("1265-EDIT-US-SSN",ssn("666","00","0000"),"");
        assertEquals("666",restricted.get("WS-EDIT-US-SSN-PART1"));
        assertEquals("SSN Last 4 chars",restricted.get("WS-EDIT-VARIABLE-NAME").stripTrailing());
        assertEquals("SSN: First 3 chars: should not be 000, 666, or between 900 and 999",restricted.get("WS-RETURN-MSG").stripTrailing());
    }
    @Test void ficoRangeLeavesSuccessfulFlagUntouchedAndKeepsFirstError() {
        for(String prior:new String[]{"","FIRST ERROR","\0"})
            for(String value:new String[]{"000","299","300","301","849","850","851","999","4A0","3A0","   ","\0\0\0"})
                compare("1275-EDIT-FICO-SCORE",Map.of("ACUP-NEW-CUST-FICO-SCORE-X",value),prior);
        var accepted=compare("1275-EDIT-FICO-SCORE",Map.of("ACUP-NEW-CUST-FICO-SCORE-X","300"),"");
        assertEquals("B",accepted.get("WS-EDIT-FICO-SCORE-FLGS"));assertFalse(accepted.condition("INPUT-ERROR"));
        var rejected=compare("1275-EDIT-FICO-SCORE",Map.of("ACUP-NEW-CUST-FICO-SCORE-X","851"),"");
        assertEquals("0",rejected.get("WS-EDIT-FICO-SCORE-FLGS"));
        assertEquals("FICO Score: should be between 300 and 850",rejected.get("WS-RETURN-MSG").stripTrailing());
    }
    @Test void migratedParagraphsAreAbsentFromProductionModel() {
        for(String paragraph:new String[]{"1265-EDIT-US-SSN","1275-EDIT-FICO-SCORE"}) {
            assertFalse(model.path("validation").path("paragraphs").has(paragraph));
            assertTrue(model.path("validation").path("native_paragraphs").has(paragraph));
            assertTrue(model.path("generic_edits").path("paragraphs").has(paragraph));
        }
        assertTrue(model.path("validation").path("paragraphs").has("1260-EDIT-US-PHONE-NUM"));
    }
}
