package ai.lightyear.carddemo;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static ai.lightyear.carddemo.AccountInputRules.Outcome.*;
import static org.junit.jupiter.api.Assertions.*;

class AccountInputRulesTest {
    private JsonNode model() throws Exception {
        return JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
    }
    @Test void requiredFieldPreservesSeparateLowValuesAndSpacesQuirk() {
        for(String value:new String[]{" ","   ","\0","\0\0\0"})
            assertEquals(MISSING,AccountInputRules.validateRequired(value));
        for(String value:new String[]{" \0","\0 ","\t","0","a"," a ","\0a"})
            assertEquals(VALID,AccountInputRules.validateRequired(value));
    }
    @Test void yesNoPreservesCaseAndZeroBlankQuirks() {
        for(char c=0;c<128;c++) {
            var expected=c=='Y'||c=='N'?VALID:c==0||c==' '||c=='0'?MISSING:INVALID;
            assertEquals(expected,AccountInputRules.validateYesNo(c),"character "+(int)c);
        }
    }
    @Test void productionHasNoStatementBodiesForCompletedRules() throws Exception {
        var m=model().path("validation");
        for(String p:new String[]{"1215-EDIT-MANDATORY","1220-EDIT-YESNO"}) {
            assertFalse(m.path("paragraphs").has(p));
            assertEquals("AccountInputRules",m.path("native_paragraphs").path(p).asText());
            assertTrue(model().path("generic_edits").path("paragraphs").has(p));
        }
        assertTrue(m.path("paragraphs").has("1250-EDIT-SIGNED-9V2"));
    }
    private void compareRule(String paragraph,String value,int length,String priorError) throws Exception {
        var m=model();var oracle=new SourceEdits(m.path("generic_edits"));
        var candidate=new SourceEdits(m.path("validation"));
        for(var e:new SourceEdits[]{oracle,candidate}) {
            e.put("WS-EDIT-VARIABLE-NAME","  ABCDEFGHIJKLMNOPQRSTUVWXYZ");
            e.put("WS-EDIT-ALPHANUM-ONLY",value);
            e.put("WS-EDIT-ALPHANUM-LENGTH",Integer.toString(length));
            e.put("WS-EDIT-YES-NO",value);
            e.put("WS-RETURN-MSG",priorError);
            e.setCondition("FLG-MANDATORY-NOT-OK");
            e.run(paragraph);
        }
        for(String field:new String[]{"WS-EDIT-MANDATORY-FLAGS","WS-EDIT-YES-NO",
                "WS-EDIT-ALPHANUM-ONLY","WS-EDIT-VARIABLE-NAME","WS-RETURN-MSG"})
            assertEquals(oracle.get(field),candidate.get(field),paragraph+" "+field);
        assertEquals(oracle.condition("INPUT-ERROR"),candidate.condition("INPUT-ERROR"));
        assertFalse(candidate.trace().isEmpty());
    }
    @Test void storageAdapterMatchesOldRulesAndPreservesFirstError() throws Exception {
        for(String prior:new String[]{"","FIRST ERROR","\0"}) {
            for(char c=0;c<128;c++)compareRule("1220-EDIT-YESNO",String.valueOf(c),1,prior);
            for(String value:new String[]{"","\0\0\0","   ","\0  ","  \0","a","0","  a","\t"})
                for(int length:new int[]{1,3,256})compareRule("1215-EDIT-MANDATORY",value,length,prior);
        }
    }
}
