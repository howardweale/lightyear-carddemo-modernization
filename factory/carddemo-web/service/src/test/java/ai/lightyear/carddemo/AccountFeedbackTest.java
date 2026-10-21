package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
import tools.jackson.databind.json.JsonMapper;
import static ai.lightyear.carddemo.AccountValidationFeedback.*;
import static org.junit.jupiter.api.Assertions.*;

/** CI-only oracle: original statement bodies and every storage byte remain independent. */
class AccountFeedbackTest {
    private static JsonNode original,production;
    @BeforeAll static void load() throws Exception {
        JsonNode update=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
        ObjectNode copy=(ObjectNode)update.path("validation").deepCopy();
        copy.remove("native_paragraphs");
        ObjectNode paragraphs=(ObjectNode)copy.path("paragraphs");
        for(var entry:update.path("generic_edits").path("paragraphs").properties())
            paragraphs.set(entry.getKey(),entry.getValue());
        original=copy;production=update.path("validation");
    }
    private static void completeStorage(SourceEdits expected,SourceEdits actual) throws Exception {
        var storage=SourceEdits.class.getDeclaredField("storage");storage.setAccessible(true);
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        assertArrayEquals(((Commarea)storage.get(expected)).bytes(),((Commarea)storage.get(actual)).bytes());
        assertEquals(values.get(expected),values.get(actual));
    }
    @Test void sourceFlagsKeepLowValuesMissingInvalidAndYesNoDistinct() {
        assertEquals("\0",Flag.VALID.display());assertEquals("B",Flag.MISSING.display());
        assertEquals("0",Flag.INVALID.display());
        assertEquals(Flag.VALID,flag(AccountInputRules.Outcome.VALID));
        assertEquals(Flag.MISSING,flag(AccountInputRules.Outcome.MISSING));
        assertEquals(Flag.INVALID,flag(AccountInputRules.Outcome.INVALID));
        assertEquals(Flag.VALID,flag(AccountTextRules.Status.VALID));
        assertEquals(Flag.MISSING,flag(AccountTextRules.Status.MISSING));
        assertEquals(Flag.INVALID,flag(AccountTextRules.Status.INVALID));
        assertEquals(Flag.INVALID,flag(AccountTextRules.Status.ZERO));
        assertEquals("WS-INPUT-FLAG",Field.INPUT_FLAG.storage());
        assertEquals("WS-RETURN-MSG",Field.MESSAGE.storage());
        assertEquals("WS-EDIT-VARIABLE-NAME",Field.LABEL.storage());
    }
    @Test void everyMessageKeepsSpaceOnlyTrimmingAndFirstError() {
        Map<Reason,String> suffixes=new LinkedHashMap<>();
        suffixes.put(Reason.REQUIRED," must be supplied.");suffixes.put(Reason.YES_NO," must be Y or N.");
        suffixes.put(Reason.ALPHA," can have alphabets only.");suffixes.put(Reason.ALPHANUM," can have numbers or alphabets only.");
        suffixes.put(Reason.NUMERIC," must be all numeric.");suffixes.put(Reason.NONZERO," must not be zero.");
        suffixes.put(Reason.MONEY," is not valid");suffixes.put(Reason.SSN_RANGE,": should not be 000, 666, or between 900 and 999");
        suffixes.put(Reason.FICO_RANGE,": should be between 300 and 850");suffixes.put(Reason.STATE,": is not a valid state code");
        suffixes.put(Reason.STATE_ZIP,"Invalid zip code for state");
        assertEquals(Reason.values().length,suffixes.size());
        String[][] labels={{"  Name  ","Name"},{"A","A"},{"   ",""},{"",""},{"\tName\t","\tName\t"},{" \0 ","\0"}};
        for(var item:suffixes.entrySet())for(String[] label:labels)for(boolean off:new boolean[]{false,true}) {
            Map<Field,String> values=new LinkedHashMap<>(Map.of(Field.INPUT_FLAG,"0",Field.MESSAGE,"FIRST",Field.LABEL,label[0]));
            State state=new State() {
                public String get(Field field) { return values.get(field); }
                public void put(Field field,String value) { values.put(field,value); }
                public boolean messageOff() { return off; }
            };
            error(state,item.getKey());
            assertEquals("1",values.get(Field.INPUT_FLAG));
            assertEquals(off?(item.getKey()==Reason.STATE_ZIP?item.getValue():label[1]+item.getValue()):"FIRST",values.get(Field.MESSAGE));
            assertEquals(label[0],values.get(Field.LABEL));
        }
    }
    @Test void typedAdapterPreservesFixedWidthsAndOriginalMessageOffPredicate() {
        for(String prior:new String[]{"","FIRST","\0","\t"}) {
            SourceEdits edits=new SourceEdits(production);AccountFeedbackState state=new AccountFeedbackState(edits);
            state.put(Field.LABEL,"ABCDEFGHIJKLMNOPQRSTUVWXYZ");
            assertEquals("ABCDEFGHIJKLMNOPQRSTUVWXY",state.get(Field.LABEL));
            state.put(Field.MESSAGE,prior);
            assertEquals(prior.isEmpty(),state.messageOff());
            String before=edits.get("WS-RETURN-MSG");
            error(state,Reason.SSN_RANGE);
            assertEquals("1",state.get(Field.INPUT_FLAG));
            String expected="ABCDEFGHIJKLMNOPQRSTUVWXY: should not be 000, 666, or between 900 and 999";
            assertEquals(prior.isEmpty()?(expected+" ".repeat(75)).substring(0,75):before,state.get(Field.MESSAGE));
            String first=state.get(Field.MESSAGE);error(state,Reason.STATE_ZIP);
            assertEquals(first,state.get(Field.MESSAGE));
        }
    }
    @Test void allNativeFeedbackPathsPreserveEveryStorageByte() throws Exception {
        Map<String,String[]> cases=new LinkedHashMap<>();
        cases.put("1215-EDIT-MANDATORY",new String[]{" ","\0","A"});
        cases.put("1220-EDIT-YESNO",new String[]{"Y","N","?"," ","0","\0"});
        cases.put("1225-EDIT-ALPHA-REQD",new String[]{" ","\0","Ada","A1","A-"});
        cases.put("1230-EDIT-ALPHANUM-REQD",new String[]{" ","A1","A@"});
        cases.put("1235-EDIT-ALPHA-OPT",new String[]{" ","Ada","A1"});
        cases.put("1240-EDIT-ALPHANUM-OPT",new String[]{" ","A1","@"});
        cases.put("1245-EDIT-NUM-REQD",new String[]{" ","0","12","X1"});
        cases.put("1250-EDIT-SIGNED-9V2",new String[]{" ","-12.34","0","X"});
        cases.put("1265-EDIT-US-SSN",new String[]{"123","000","666","900"," ","1X3"});
        cases.put("1270-EDIT-US-STATE-CD",new String[]{"OR","or","ZZ"," ","\0"});
        cases.put("1275-EDIT-FICO-SCORE",new String[]{"299","300","850","851","ABC"});
        cases.put("1280-EDIT-US-STATE-ZIP-CD",new String[]{"97ABC","34000","9 ABC"," ","\0"});
        int compared=0;
        for(var item:cases.entrySet())for(String value:item.getValue())
            for(String prior:new String[]{"","FIRST","\0"})for(String input:new String[]{"0","1","\0"})
                for(String label:new String[]{"  Name  ","ABCDEFGHIJKLMNOPQRSTUVWXYZ"," \0 "}) {
                    SourceEdits oracle=new SourceEdits(original),actual=new SourceEdits(production);
                    for(SourceEdits edits:new SourceEdits[]{oracle,actual}) {
                        edits.put("WS-INPUT-FLAG",input);edits.put("WS-RETURN-MSG",prior);
                        edits.put("WS-EDIT-VARIABLE-NAME",label);
                        edits.put("WS-EDIT-ALPHANUM-ONLY",value);
                        edits.put("WS-EDIT-ALPHANUM-LENGTH",Integer.toString(value.length()));
                        edits.put("WS-EDIT-YES-NO",value);
                        edits.put("WS-EDIT-SIGNED-NUMBER-9V2-X",value);
                        edits.put("ACUP-NEW-CUST-SSN-1",value);
                        edits.put("ACUP-NEW-CUST-SSN-2","00");edits.put("ACUP-NEW-CUST-SSN-3","12X4");
                        edits.put("ACUP-NEW-CUST-ADDR-STATE-CD",item.getKey().equals("1280-EDIT-US-STATE-ZIP-CD")?"OR":value);
                        edits.put("ACUP-NEW-CUST-ADDR-ZIP",value);edits.put("ACUP-NEW-CUST-FICO-SCORE",value);
                        edits.run(item.getKey());
                    }
                    completeStorage(oracle,actual);compared++;
                }
        assertTrue(compared>1000);
    }
    @Test void byteAndScratchMismatchCannotPassTheOracle() throws Exception {
        var oracle=new SourceEdits(original);var actual=new SourceEdits(production);
        completeStorage(oracle,actual);
        actual.put("WS-INPUT-FLAG","1");
        assertThrows(AssertionError.class,()->completeStorage(oracle,actual));
        actual.put("WS-INPUT-FLAG",oracle.get("WS-INPUT-FLAG"));completeStorage(oracle,actual);
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        @SuppressWarnings("unchecked") var scratch=(Map<String,String>)values.get(actual);
        scratch.put("fixture-mismatch","different");
        assertThrows(AssertionError.class,()->completeStorage(oracle,actual));
    }
}
