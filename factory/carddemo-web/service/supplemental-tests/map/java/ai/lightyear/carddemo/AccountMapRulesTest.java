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

/** CI-only oracle: original statement bodies, all storage bytes and scratch values. */
class AccountMapRulesTest {
    private static JsonNode raw,original,production;
    private static final Clock CLOCK=Clock.fixed(Instant.parse("2026-10-22T12:00:00Z"),ZoneOffset.UTC);
    private static final List<String> PARAGRAPHS=List.of("1100-RECEIVE-MAP","1200-EDIT-MAP-INPUTS","1205-COMPARE-OLD-NEW","1210-EDIT-ACCOUNT");
    @BeforeAll static void load() throws Exception {
        JsonNode update=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
        raw=update.path("validation");ObjectNode copy=(ObjectNode)raw.deepCopy();copy.remove("native_paragraphs");
        for(var entry:update.path("generic_edits").path("paragraphs").properties())
            ((ObjectNode)copy.path("paragraphs")).set(entry.getKey(),entry.getValue());
        original=copy;production=AccountMapModel.retire(raw);
    }
    private static Commarea storage(SourceEdits e) throws Exception {
        var f=SourceEdits.class.getDeclaredField("storage");f.setAccessible(true);return (Commarea)f.get(e);
    }
    private static void same(SourceEdits a,SourceEdits b) throws Exception {
        assertArrayEquals(storage(a).bytes(),storage(b).bytes());
        var f=SourceEdits.class.getDeclaredField("values");f.setAccessible(true);assertEquals(f.get(a),f.get(b));
    }
    private static SourceEdits[] pair(){return new SourceEdits[]{new SourceEdits(original,CLOCK),new SourceEdits(production,CLOCK)};}
    private static void run(SourceEdits[] p,String paragraph) throws Exception {p[0].run(paragraph);p[1].run(paragraph);same(p[0],p[1]);}
    private static List<String> inputs() {
        List<String> names=new ArrayList<>();
        for(var entry:raw.path("fields").properties())
            if(entry.getValue().path("screen_part").asText().equals("I"))names.add(entry.getKey());
        return names;
    }
    private static void seed(SourceEdits e,boolean fetched) {
        for(String name:inputs())e.put(name,"");
        e.setCondition(fetched?"ACUP-SHOW-DETAILS":"ACUP-DETAILS-NOT-FETCHED");e.put("ACCTSIDI","12345678901");
    }
    private static void valid(SourceEdits e) {
        seed(e,true);
        String[][] input={
            {"ACSTTUSI","Y"},{"ACRDLIMI","100.00"},{"ACSHLIMI","50.00"},{"ACURBALI","25.00"},
            {"ACRCYCRI","5.00"},{"ACRCYDBI","2.00"},{"AADDGRPI","GROUP"},{"ACSTNUMI","123456789"},
            {"ACTSSN1I","123"},{"ACTSSN2I","45"},{"ACTSSN3I","6789"},{"DOBYEARI","1980"},
            {"DOBMONI","01"},{"DOBDAYI","15"},{"ACSTFCOI","700"},{"ACSFNAMI","Ada"},{"ACSLNAMI","Lovelace"},
            {"ACSADL1I","1 Main Street"},{"ACSCITYI","Portland"},{"ACSSTTEI","OR"},{"ACSCTRYI","USA"},
            {"ACSZIPCI","97001"},{"ACSGOVTI","ID"},{"ACSEFTCI","1234567890"},{"ACSPFLGI","Y"}};
        for(String[] row:input)e.put(row[0],row[1]);
        for(String prefix:List.of("OPN","EXP","RIS")) {
            e.put(prefix+"YEARI",prefix.equals("EXP")?"2030":"2020");e.put(prefix+"MONI","01");e.put(prefix+"DAYI","15");
        }
        for(String n:List.of("1","2")){e.put("ACSPH"+n+"AI","206");e.put("ACSPH"+n+"BI","555");e.put("ACSPH"+n+"CI","0101");}
    }
    private static void copyOld(SourceEdits e) throws Exception {storage(e).move("ACUP-OLD-DETAILS",storage(e).get("ACUP-NEW-DETAILS"));}
    @Test void exactRetirementAndClosedBindingsRefuseMissingOrUnexpectedBodies() {
        String before=raw.toString();JsonNode retired=AccountMapModel.retire(raw);assertEquals(before,raw.toString());
        assertEquals(Set.copyOf(PARAGRAPHS),AccountMapModel.RULES.keySet());
        for(String paragraph:PARAGRAPHS) {
            assertFalse(retired.path("paragraphs").has(paragraph));assertEquals("AccountMapRules",retired.path("native_paragraphs").path(paragraph).asText());
            for(String kind:List.of("missing","empty","wrong","native")) {
                ObjectNode bad=(ObjectNode)raw.deepCopy();ObjectNode bodies=(ObjectNode)bad.path("paragraphs");
                switch(kind) {
                    case "missing" -> bodies.remove(paragraph);
                    case "empty" -> bodies.putArray(paragraph);
                    case "wrong" -> bodies.put(paragraph,"wrong");
                    case "native" -> ((ObjectNode)bad.path("native_paragraphs")).put(paragraph,"wrong");
                }
                assertThrows(IllegalArgumentException.class,()->AccountMapModel.retire(bad));
            }
        }
        for(var entry:raw.path("paragraphs").properties())
            if(!PARAGRAPHS.contains(entry.getKey())&&!AccountPhoneDateModel.RULES.containsKey(entry.getKey()))
                assertEquals(entry.getValue(),retired.path("paragraphs").path(entry.getKey()));
        assertThrows(IllegalArgumentException.class,()->AccountMapModel.retire(retired));
        for(var f:AccountMapState.Field.values())assertTrue(raw.path("fields").has(f.name().replace('_','-')),f.name());
        for(var f:AccountMapState.Flag.values())assertTrue(raw.path("conditions").has(f.name().replace('_','-')),f.name());
    }
    @Test void everyInputPreservesSentinelsRawDisplayAndMoneyOverlays() throws Exception {
        int count=0;
        for(String name:inputs())for(boolean fetched:new boolean[]{false,true})
            for(String value:new String[]{"","*","*X","0","\0","\0 "," A ","-12.34","$1,234.56","ABC","12345678901234567890"}) {
                var p=pair();
                for(var e:p){seed(e,fetched);e.put(name,value);storage(e).move("ACUP-NEW-DETAILS","Z".repeat(storage(e).get("ACUP-NEW-DETAILS").length()));e.put("WS-RETURN-MSG","FIRST");}
                boolean overflow=fetched && value.equals("12345678901234567890") &&
                    Set.of("ACRDLIMI","ACSHLIMI","ACURBALI","ACRCYCRI","ACRCYDBI").contains(name);
                if(overflow) {
                    for(var e:p)assertEquals("commarea-number-range",
                        assertThrows(IllegalArgumentException.class,()->e.run("1100-RECEIVE-MAP")).getMessage());
                    same(p[0],p[1]);
                } else run(p,"1100-RECEIVE-MAP");
                count++;
            }
        assertTrue(count>=900);
    }
    @Test void accountBranchesPreserveFirstMessageAndAllIdSideEffects() throws Exception {
        for(String key:new String[]{"","\0".repeat(11)," \0 ","00000000000","12345678901","123","1A345678901","-1234567890"})
            for(String message:new String[]{"","FIRST","\0"," "}) {
                var p=pair();
                for(var e:p){e.put("CC-ACCT-ID",key);e.put("WS-RETURN-MSG",message);e.put("CDEMO-ACCT-ID","99999999999");e.put("ACUP-NEW-ACCT-ID","99999999999");}
                run(p,"1210-EDIT-ACCOUNT");
            }
    }
    @Test void everyComparedFieldKeepsItsCaseWhitespaceAndBytePolicy() throws Exception {
        List<String> names=List.of("ACUP-NEW-ACCT-ID-X","ACUP-NEW-ACTIVE-STATUS","ACUP-NEW-CURR-BAL","ACUP-NEW-CREDIT-LIMIT","ACUP-NEW-CASH-CREDIT-LIMIT","ACUP-NEW-OPEN-DATE","ACUP-NEW-EXPIRAION-DATE","ACUP-NEW-REISSUE-DATE","ACUP-NEW-CURR-CYC-CREDIT","ACUP-NEW-CURR-CYC-DEBIT","ACUP-NEW-GROUP-ID","ACUP-NEW-CUST-ID-X","ACUP-NEW-CUST-FIRST-NAME","ACUP-NEW-CUST-MIDDLE-NAME","ACUP-NEW-CUST-LAST-NAME","ACUP-NEW-CUST-ADDR-LINE-1","ACUP-NEW-CUST-ADDR-LINE-2","ACUP-NEW-CUST-ADDR-LINE-3","ACUP-NEW-CUST-ADDR-STATE-CD","ACUP-NEW-CUST-ADDR-COUNTRY-CD","ACUP-NEW-CUST-ADDR-ZIP","ACUP-NEW-CUST-PHONE-NUM-1A","ACUP-NEW-CUST-PHONE-NUM-1B","ACUP-NEW-CUST-PHONE-NUM-1C","ACUP-NEW-CUST-PHONE-NUM-2A","ACUP-NEW-CUST-PHONE-NUM-2B","ACUP-NEW-CUST-PHONE-NUM-2C","ACUP-NEW-CUST-SSN-X","ACUP-NEW-CUST-GOVT-ISSUED-ID","ACUP-NEW-CUST-DOB-YYYY-MM-DD","ACUP-NEW-CUST-EFT-ACCOUNT-ID","ACUP-NEW-CUST-PRI-HOLDER-IND","ACUP-NEW-CUST-FICO-SCORE-X");assertEquals(33,names.size());
        for(String name:names)for(String variant:List.of("empty","lower","upper","leading-space","literal-x","low","zero","digits")) {
            var p=pair();
            for(var e:p){
                valid(e);e.run("1100-RECEIVE-MAP");copyOld(e);String current=storage(e).get(name);
                String value=switch(variant) {
                    case "empty" -> "";
                    case "lower" -> current.toLowerCase(Locale.ROOT);
                    case "upper" -> current.toUpperCase(Locale.ROOT);
                    case "leading-space" -> " "+current.stripTrailing();
                    case "literal-x" -> " X ";
                    case "low" -> "\0";
                    case "zero" -> "00000000000";
                    default -> "12345678901";
                };
                storage(e).move(name,ScreenFrame.pad(value,current.length()));
            }
            run(p,"1205-COMPARE-OLD-NEW");
        }
    }
    @Test void earlyExitsKeepSearchAndChangeStateFlags() throws Exception {
        for(String state:new String[]{"ACUP-DETAILS-NOT-FETCHED","ACUP-SHOW-DETAILS","ACUP-CHANGES-OK-NOT-CONFIRMED","ACUP-CHANGES-OKAYED-AND-DONE"})
            for(boolean changed:new boolean[]{false,true})for(String key:new String[]{"","00000000000","12345678901"}) {
                var p=pair();
                for(var e:p){valid(e);e.run("1100-RECEIVE-MAP");copyOld(e);if(changed)e.put("ACUP-OLD-ACCT-ID-X","99999999999");
                    e.setCondition(state);e.put("CC-ACCT-ID",key);e.put("WS-NON-KEY-FLAGS","Z".repeat(e.get("WS-NON-KEY-FLAGS").length()));}
                run(p,"1200-EDIT-MAP-INPUTS");
            }
    }
    @Test void orderedValidationKeepsFirstErrorAndEveryScratchByte() throws Exception {
        for(String name:inputs())for(String value:new String[]{"","?","\0","0","BAD"})for(String prior:new String[]{"","FIRST","\0"}) {
            var p=pair();
            for(var e:p){valid(e);e.put(name,value);e.run("1100-RECEIVE-MAP");copyOld(e);e.put("ACUP-OLD-ACCT-ID-X","99999999999");e.put("WS-RETURN-MSG",prior);}
            run(p,"1200-EDIT-MAP-INPUTS");
        }
        var good=pair();
        for(var e:good){valid(e);e.run("1100-RECEIVE-MAP");copyOld(e);e.put("ACUP-OLD-ACCT-ID-X","99999999999");}
        run(good,"1200-EDIT-MAP-INPUTS");assertFalse(good[1].condition("INPUT-ERROR"));assertTrue(good[1].condition("ACUP-CHANGES-OK-NOT-CONFIRMED"));
    }
    @Test void oracleRejectsBothStorageAndScratchCorruption() throws Exception {
        var p=pair();same(p[0],p[1]);p[1].put("WS-INPUT-FLAG","1");assertThrows(AssertionError.class,()->same(p[0],p[1]));
        p[1].put("WS-INPUT-FLAG",p[0].get("WS-INPUT-FLAG"));same(p[0],p[1]);
        var f=SourceEdits.class.getDeclaredField("values");f.setAccessible(true);
        @SuppressWarnings("unchecked") var values=(Map<String,String>)f.get(p[1]);
        values.put("mismatch","x");assertThrows(AssertionError.class,()->same(p[0],p[1]));
    }
}
