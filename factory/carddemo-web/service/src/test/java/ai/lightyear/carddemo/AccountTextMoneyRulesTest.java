package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static ai.lightyear.carddemo.AccountTextRules.Status.*;
import static org.junit.jupiter.api.Assertions.*;

class AccountTextMoneyRulesTest {
    private static JsonNode model;
    @BeforeAll static void load() throws Exception {
        model=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
    }
    @Test void exactAsciiAlphabetAndDigitBoundaries() {
        for(char c=0;c<128;c++) {
            String value=String.valueOf(c);
            boolean empty=c==0||c==' ';
            boolean letter=c>='A'&&c<='Z'||c>='a'&&c<='z';
            boolean digit=c>='0'&&c<='9';
            var name=AccountTextRules.requiredName(value);
            var text=AccountTextRules.requiredText(value);
            assertEquals(empty?MISSING:letter?VALID:INVALID,name.status(),"name "+(int)c);
            assertEquals(empty?MISSING:letter||digit?VALID:INVALID,text.status(),"text "+(int)c);
            assertEquals(letter?" ":value,name.scratch());
            assertEquals(letter||digit?" ":value,text.scratch());
            assertEquals(!empty,name.converted());assertEquals(!empty,text.converted());
            assertEquals(empty||letter?VALID:INVALID,AccountTextRules.optionalName(value).status());
            assertEquals(empty||letter||digit?VALID:INVALID,AccountTextRules.optionalText(value).status());
            var number=AccountTextRules.requiredNonzeroDigits(value);
            assertEquals(empty?MISSING:!digit?INVALID:c=='0'?ZERO:VALID,number.status());
            assertEquals(value,number.scratch());assertFalse(number.converted());
        }
    }
    @Test void scratchConversionKeepsMixedNullAndWhitespaceQuirks() {
        assertEquals("   !\0\t",AccountTextRules.requiredName("aZ !\0\t").scratch());
        assertEquals("    !\0\t",AccountTextRules.requiredText("aZ9 !\0\t").scratch());
        for(String value:new String[]{"\0 "," \0","Ã©","\t","Ù¡"}) {
            assertEquals(INVALID,AccountTextRules.optionalText(value).status());
            assertEquals(INVALID,AccountTextRules.requiredNonzeroDigits(value).status());
        }
        for(String value:new String[]{"000","0".repeat(256)})
            assertEquals(ZERO,AccountTextRules.requiredNonzeroDigits(value).status());
        assertEquals(VALID,AccountTextRules.requiredNonzeroDigits("0".repeat(255)+"1").status());
        assertEquals(VALID,AccountTextRules.requiredName(" A z ").status());
        assertEquals(VALID,AccountTextRules.requiredText(" A 1 z ").status());
        assertEquals(VALID,AccountTextRules.optionalName("\0\0").status());
        assertEquals("\0\0",AccountTextRules.optionalName("\0\0").scratch());
        assertFalse(AccountTextRules.optionalName("\0\0").converted());
        assertEquals(VALID,AccountTextRules.optionalText("   ").status());
        assertEquals("   ",AccountTextRules.optionalText("   ").scratch());
        assertFalse(AccountTextRules.optionalText("   ").converted());
    }
    @Test void moneyPreservesSignCurrencyZeroAndUnrestrictedScale() {
        String[][] values={{"0","0"},{"-0.00","0.00"},{" + $ 1,234.50 ","1234.50"},
            {"$1,23 DB","-123"},{".25CR","-0.25"},{"1.-","-1"},{".5+","0.5"},
            {"- 1.234","-1.234"},{"123456789012345","123456789012345"}};
        for(String[] pair:values) {
            var result=AccountMoneyRule.validate(pair[0]);
            assertEquals(AccountInputRules.Outcome.VALID,result.outcome(),pair[0]);
            assertEquals(new BigDecimal(pair[1]),result.amount(),pair[0]);
        }
        for(String value:new String[]{" ","   ","\0\0"}) {
            var result=AccountMoneyRule.validate(value);
            assertEquals(AccountInputRules.Outcome.MISSING,result.outcome());assertNull(result.amount());
        }
        for(String value:new String[]{" \0","\0 ","$","+","-1-","+1CR","1DB+", "1 cr",
                "1\t","1,","1,,2","1.2.3","$-1","1234567890123456"}) {
            var result=AccountMoneyRule.validate(value);
            assertEquals(AccountInputRules.Outcome.INVALID,result.outcome(),value);assertNull(result.amount());
        }
    }
    private void compare(String paragraph,String input,int length,String prior) {
        var oracle=new SourceEdits(model.path("generic_edits"));
        var candidate=new SourceEdits(model.path("validation"));
        for(var e:new SourceEdits[]{oracle,candidate}) {
            e.put("WS-EDIT-VARIABLE-NAME","  ABCDEFGHIJKLMNOPQRSTUVWXYZ");
            e.put("WS-EDIT-ALPHANUM-ONLY",input);
            e.put("WS-EDIT-ALPHANUM-LENGTH",Integer.toString(length));
            e.put("WS-EDIT-SIGNED-NUMBER-9V2-X",input);
            e.put("WS-RETURN-MSG",prior);
            e.run(paragraph);
        }
        for(String field:new String[]{"WS-EDIT-ALPHA-ONLY-FLAGS","WS-EDIT-ALPHANUM-ONLY-FLAGS",
                "WS-EDIT-ALPHANUM-ONLY","WS-EDIT-SIGNED-NUMBER-9V2-X","WS-FLG-SIGNED-NUMBER-EDIT",
                "WS-RETURN-MSG","LIT-ALL-ALPHA-FROM","LIT-ALL-ALPHANUM-FROM"})
            assertEquals(oracle.get(field),candidate.get(field),paragraph+" "+field+" length="+length);
        assertEquals(oracle.condition("INPUT-ERROR"),candidate.condition("INPUT-ERROR"));
        assertFalse(candidate.trace().isEmpty());
    }
    @Test void storageOracleCoversPrefixMutationFirstErrorAndMoneyFlags() {
        for(String prior:new String[]{"","FIRST ERROR","\0"}) {
            for(String input:new String[]{"","\0".repeat(256)," \0","\t","Alice Smith","A9! tail",
                    "12345EXTRA","00000","09","Ã©","Az09".repeat(64)})
                for(int length:new int[]{1,3,5,256})
                    for(String rule:new String[]{"1225-EDIT-ALPHA-REQD","1230-EDIT-ALPHANUM-REQD",
                            "1235-EDIT-ALPHA-OPT","1240-EDIT-ALPHANUM-OPT","1245-EDIT-NUM-REQD"})
                        compare(rule,input,length,prior);
            for(String input:new String[]{"","\0".repeat(15)," \0","0","-1.23"," $ 1,23 CR ","+1-","1,",".1","1.234"})
                compare("1250-EDIT-SIGNED-9V2",input,15,prior);
        }
    }
    @Test void completedRulesHaveNoProductionStatementBodies() {
        for(String rule:new String[]{"1225-EDIT-ALPHA-REQD","1230-EDIT-ALPHANUM-REQD",
                "1235-EDIT-ALPHA-OPT","1240-EDIT-ALPHANUM-OPT","1245-EDIT-NUM-REQD","1250-EDIT-SIGNED-9V2"}) {
            assertFalse(model.path("validation").path("paragraphs").has(rule));
            assertTrue(model.path("validation").path("native_paragraphs").has(rule));
            assertTrue(model.path("generic_edits").path("paragraphs").has(rule));
        }
        assertTrue(model.path("validation").path("paragraphs").has("1260-EDIT-US-PHONE-NUM"));
    }
}
