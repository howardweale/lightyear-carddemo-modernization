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

/** Draft CI oracle. Cases follow COACTUPC 2698-3586; no local execution. */
class AccountRenderRulesTest {
    private static JsonNode raw,original,production;
    private static Bindings bindings;
    private static final Clock CLOCK=Clock.fixed(Instant.parse("2026-10-22T12:00:00Z"),ZoneOffset.UTC);
    private static final List<String> PARAGRAPHS=List.of("3200-SETUP-SCREEN-VARS","3201-SHOW-INITIAL-VALUES",
        "3202-SHOW-ORIGINAL-VALUES","3203-SHOW-UPDATED-VALUES","3250-SETUP-INFOMSG",
        "3300-SETUP-SCREEN-ATTRS","3310-PROTECT-ALL-ATTRS","3320-UNPROTECT-FEW-ATTRS","3390-SETUP-INFOMSG-ATTRS");
    private static final List<String> ACTIONS=List.of("ACUP-DETAILS-NOT-FETCHED","ACUP-SHOW-DETAILS",
        "ACUP-CHANGES-NOT-OK","ACUP-CHANGES-OK-NOT-CONFIRMED","ACUP-CHANGES-OKAYED-AND-DONE",
        "ACUP-CHANGES-OKAYED-LOCK-ERROR","ACUP-CHANGES-OKAYED-BUT-FAILED");
    @BeforeAll static void load() throws Exception {
        Path root=Path.of(System.getProperty("carddemo.root"));
        bindings=new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),
            root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build(),CLOCK);
        JsonNode update=bindings.root.path("account_update");raw=update.path("validation");
        ObjectNode copy=(ObjectNode)raw.deepCopy();copy.remove("native_paragraphs");
        for(var entry:update.path("generic_edits").path("paragraphs").properties())
            ((ObjectNode)copy.path("paragraphs")).set(entry.getKey(),entry.getValue());
        original=copy;production=AccountRenderModel.retire(raw);
    }
    private record Lane(SourceEdits edits,ScreenFrame screen) {}
    private static Lane lane(JsonNode model) {
        ScreenFrame screen=new ScreenFrame(bindings,"COACTUPC",CLOCK);
        for(String field:screen.values.keySet())screen.set(field,"STALE-"+field);
        for(var attrs:screen.attributes.values()) {
            attrs.put("protected",false);attrs.put("hidden",true);attrs.put("color","BLUE");
            attrs.put("modified",false);attrs.put("highlight","UNDERLINE");
        }
        screen.cursor="ACSEFTC";screen.message="OLD ERROR";screen.endpoint="unchanged";
        SourceEdits edits=new SourceEdits(model,CLOCK);edits.attachScreen(screen);
        // COACTUPC 2797-2813 reads signed numeric REDEFINES after a master read.
        // Their PIC X base fields initialize to spaces; seed valid account money in both lanes.
        for(String name:List.of("CURR-BAL","CREDIT-LIMIT","CASH-CREDIT-LIMIT","CURR-CYC-CREDIT","CURR-CYC-DEBIT"))
            edits.put("ACUP-OLD-"+name+"-N","0.00");
        return new Lane(edits,screen);
    }
    private static Lane[] pair(){return new Lane[]{lane(original),lane(production)};}
    private static Commarea storage(SourceEdits e) throws Exception {
        var f=SourceEdits.class.getDeclaredField("storage");f.setAccessible(true);return (Commarea)f.get(e);
    }
    private static void same(Lane a,Lane b) throws Exception {
        assertArrayEquals(storage(a.edits).bytes(),storage(b.edits).bytes());
        var f=SourceEdits.class.getDeclaredField("values");f.setAccessible(true);assertEquals(f.get(a.edits),f.get(b.edits));
        assertEquals(a.screen.values,b.screen.values);assertEquals(a.screen.attributes,b.screen.attributes);
        assertEquals(a.screen.cursor,b.screen.cursor);assertEquals(a.screen.message,b.screen.message);
        assertEquals(a.screen.endpoint,b.screen.endpoint);
    }
    private static void run(Lane[] p,String paragraph) throws Exception {
        p[0].edits.run(paragraph);p[1].edits.run(paragraph);same(p[0],p[1]);
    }
    private static void clearFlags(SourceEdits e) {
        e.mapLow("WS-NON-KEY-FLAGS");e.setCondition("FLG-ACCTFILTER-ISVALID");
        e.setCondition("ACUP-SHOW-DETAILS");e.setCondition("CDEMO-PGM-REENTER");
    }
    @Test void exactRetirementPreservesOriginalAndRejectsMissingEmptyWrongOrNativeBodies() {
        String before=raw.toString();JsonNode retired=AccountRenderModel.retire(raw);
        assertEquals(before,raw.toString());assertEquals(Set.copyOf(PARAGRAPHS),AccountRenderModel.RULES.keySet());
        for(String paragraph:PARAGRAPHS) {
            assertFalse(retired.path("paragraphs").has(paragraph));
            assertEquals("AccountRenderRules",retired.path("native_paragraphs").path(paragraph).asText());
            for(String kind:List.of("missing","empty","wrong","native")) {
                ObjectNode bad=(ObjectNode)raw.deepCopy(),bodies=(ObjectNode)bad.path("paragraphs");
                switch(kind) {
                    case "missing" -> bodies.remove(paragraph);
                    case "empty" -> bodies.putArray(paragraph);
                    case "wrong" -> bodies.put(paragraph,"wrong");
                    case "native" -> ((ObjectNode)bad.path("native_paragraphs")).put(paragraph,"wrong");
                }
                assertThrows(IllegalArgumentException.class,()->AccountRenderModel.retire(bad));
            }
        }
        for(var entry:raw.path("paragraphs").properties())
            if(!PARAGRAPHS.contains(entry.getKey())&&!AccountMapModel.RULES.containsKey(entry.getKey())
                &&!AccountPhoneDateModel.RULES.containsKey(entry.getKey()))
                assertEquals(entry.getValue(),retired.path("paragraphs").path(entry.getKey()));
        assertThrows(IllegalArgumentException.class,()->AccountRenderModel.retire(retired));
    }
    // Source 2698-2785: entry no-op, zero key, action branches, LOW-VALUES leave the terminal stale.
    @Test void setupPreservesEntryAndInitialScreenSemantics() throws Exception {
        for(String action:ACTIONS)for(String phase:List.of("CDEMO-PGM-ENTER","CDEMO-PGM-REENTER"))
            for(String key:List.of("00000000000","12345678901","1A345678901")) {
                var p=pair();for(var lane:p) {
                    clearFlags(lane.edits);lane.edits.setCondition(action);lane.edits.setCondition(phase);
                    lane.edits.put("CC-ACCT-ID",key);
                }
                run(p,PARAGRAPHS.get(0));
            }
        var p=pair();Map<String,String> before=new LinkedHashMap<>(p[1].screen.values);
        run(p,PARAGRAPHS.get(1));assertEquals(before,p[1].screen.values);
    }
    // Source 2787-2869: account OR customer enables account moves, customer alone enables its fields.
    @Test void originalValuesPreserveReadFlagsMoneySlicesAndScratch() throws Exception {
        for(boolean account:new boolean[]{false,true})for(boolean customer:new boolean[]{false,true}) {
            var p=pair();for(var lane:p) {
                var e=lane.edits;e.put("WS-ACCOUNT-MASTER-READ-FLAG",account?"1":"0");
                e.put("WS-CUST-MASTER-READ-FLAG",customer?"1":"0");
                e.put("WS-NON-KEY-FLAGS","Z".repeat(e.get("WS-NON-KEY-FLAGS").length()));
                e.put("ACUP-OLD-ACTIVE-STATUS","Y");
                String[] money={"CURR-BAL","CREDIT-LIMIT","CASH-CREDIT-LIMIT","CURR-CYC-CREDIT","CURR-CYC-DEBIT"};
                for(int i=0;i<money.length;i++)e.put("ACUP-OLD-"+money[i]+"-N",(i%2==0?"-":"")+(i+1)+".23");
                e.put("ACUP-OLD-CUST-SSN-X","012345678");e.put("ACUP-OLD-CUST-FICO-SCORE-X","701");
                e.put("ACUP-OLD-CUST-PHONE-NUM-1","(206)555-0101");
                e.put("ACUP-OLD-CUST-PHONE-NUM-2","(415)987-6543");
                e.put("ACUP-OLD-CUST-FIRST-NAME","Ada");e.put("ACUP-OLD-CUST-MIDDLE-NAME","Byron");
                e.put("ACUP-OLD-CUST-LAST-NAME","Lovelace");e.put("ACUP-OLD-GROUP-ID","GRP123");
            }
            run(p,PARAGRAPHS.get(2));
            if(customer){
                assertEquals("012",p[1].screen.values.get("ACTSSN1").stripTrailing());
                assertEquals("34",p[1].screen.values.get("ACTSSN2").stripTrailing());
                assertEquals("5678",p[1].screen.values.get("ACTSSN3").stripTrailing());
                assertEquals("206",p[1].screen.values.get("ACSPH1A").stripTrailing());
                assertEquals("987",p[1].screen.values.get("ACSPH2B").stripTrailing());
                assertEquals("6543",p[1].screen.values.get("ACSPH2C").stripTrailing());
            }
        }
    }
    // Source 2795-2863 and 2870-2947: every copied old/new field varies independently.
    // Money branches are exercised separately at source 2870-2910; these operands come from COBOL.
    @Test void everyCopiedSourceFieldPreservesWholeStorageAndScreen() throws Exception {
        String[] oldFields={"ACUP-OLD-ACTIVE-STATUS","ACUP-OLD-OPEN-YEAR","ACUP-OLD-OPEN-MON",
            "ACUP-OLD-OPEN-DAY","ACUP-OLD-EXP-YEAR","ACUP-OLD-EXP-MON",
            "ACUP-OLD-EXP-DAY","ACUP-OLD-REISSUE-YEAR","ACUP-OLD-REISSUE-MON",
            "ACUP-OLD-REISSUE-DAY","ACUP-OLD-GROUP-ID","ACUP-OLD-CUST-ID-X",
            "ACUP-OLD-CUST-SSN-X","ACUP-OLD-CUST-FICO-SCORE-X","ACUP-OLD-CUST-DOB-YEAR",
            "ACUP-OLD-CUST-DOB-MON","ACUP-OLD-CUST-DOB-DAY","ACUP-OLD-CUST-FIRST-NAME",
            "ACUP-OLD-CUST-MIDDLE-NAME","ACUP-OLD-CUST-LAST-NAME","ACUP-OLD-CUST-ADDR-LINE-1",
            "ACUP-OLD-CUST-ADDR-LINE-2","ACUP-OLD-CUST-ADDR-LINE-3","ACUP-OLD-CUST-ADDR-STATE-CD",
            "ACUP-OLD-CUST-ADDR-ZIP","ACUP-OLD-CUST-ADDR-COUNTRY-CD","ACUP-OLD-CUST-PHONE-NUM-1",
            "ACUP-OLD-CUST-PHONE-NUM-2","ACUP-OLD-CUST-GOVT-ISSUED-ID","ACUP-OLD-CUST-EFT-ACCOUNT-ID",
            "ACUP-OLD-CUST-PRI-HOLDER-IND"};
        String[] newFields={"ACUP-NEW-ACTIVE-STATUS","ACUP-NEW-OPEN-YEAR","ACUP-NEW-OPEN-MON","ACUP-NEW-OPEN-DAY",
            "ACUP-NEW-EXP-YEAR","ACUP-NEW-EXP-MON","ACUP-NEW-EXP-DAY",
            "ACUP-NEW-REISSUE-YEAR","ACUP-NEW-REISSUE-MON","ACUP-NEW-REISSUE-DAY",
            "ACUP-NEW-GROUP-ID","ACUP-NEW-CUST-ID-X","ACUP-NEW-CUST-SSN-1",
            "ACUP-NEW-CUST-SSN-2","ACUP-NEW-CUST-SSN-3","ACUP-NEW-CUST-FICO-SCORE-X",
            "ACUP-NEW-CUST-DOB-YEAR","ACUP-NEW-CUST-DOB-MON","ACUP-NEW-CUST-DOB-DAY",
            "ACUP-NEW-CUST-FIRST-NAME","ACUP-NEW-CUST-MIDDLE-NAME","ACUP-NEW-CUST-LAST-NAME",
            "ACUP-NEW-CUST-ADDR-LINE-1","ACUP-NEW-CUST-ADDR-LINE-2","ACUP-NEW-CUST-ADDR-LINE-3",
            "ACUP-NEW-CUST-ADDR-STATE-CD","ACUP-NEW-CUST-ADDR-ZIP","ACUP-NEW-CUST-ADDR-COUNTRY-CD",
            "ACUP-NEW-CUST-PHONE-NUM-1A","ACUP-NEW-CUST-PHONE-NUM-1B","ACUP-NEW-CUST-PHONE-NUM-1C",
            "ACUP-NEW-CUST-PHONE-NUM-2A","ACUP-NEW-CUST-PHONE-NUM-2B","ACUP-NEW-CUST-PHONE-NUM-2C",
            "ACUP-NEW-CUST-GOVT-ISSUED-ID","ACUP-NEW-CUST-EFT-ACCOUNT-ID","ACUP-NEW-CUST-PRI-HOLDER-IND"};
        for(boolean updated:new boolean[]{false,true})for(String field:updated?newFields:oldFields)
            for(String symbol:List.of("1","Z"," ")) {
                var p=pair();for(var lane:p) {
                    clearFlags(lane.edits);lane.edits.setCondition("FOUND-ACCT-IN-MASTER");
                    lane.edits.setCondition("FOUND-CUST-IN-MASTER");
                    JsonNode definition=raw.path("fields").path(field);
                    assertFalse(definition.isMissingNode(),field);
                    int width=definition.path("length").asInt();assertTrue(width>0,field);
                    if(definition.path("type").asText().equals("number"))lane.edits.put(field,"7");
                    else if(storage(lane.edits).unsignedDisplayInteger(field))
                        storage(lane.edits).moveDisplayBytes(field,symbol.repeat(width));
                    else lane.edits.put(field,symbol.repeat(width));
                }
                run(p,PARAGRAPHS.get(updated?3:2));
            }
    }

    // Source 2870-2953: each of five money fields uses edited numeric or exact invalid display text.
    @Test void everyMoneyBranchKeepsRawTextAndSharedScratch() throws Exception {
        String[][] fields={{"CRED-LIMIT","CREDIT-LIMIT"},{"CASH-CREDIT-LIMIT","CASH-CREDIT-LIMIT"},
            {"CURR-BAL","CURR-BAL"},{"CURR-CYC-CREDIT","CURR-CYC-CREDIT"},{"CURR-CYC-DEBIT","CURR-CYC-DEBIT"}};
        for(String[] field:fields)for(String value:List.of("0.00","-12.34","1234567.89")) {
            var p=pair();for(var lane:p) {
                lane.edits.put("ACUP-NEW-"+field[1]+"-N",value);
                lane.edits.setCondition("FLG-"+field[0]+"-ISVALID");
            }
            run(p,PARAGRAPHS.get(3));
        }
        for(String[] field:fields)for(String value:List.of("BAD MONEY","*"," 12.X ","", "\0")) {
            var p=pair();for(var lane:p) {
                lane.edits.put("ACUP-NEW-"+field[1]+"-X",value);
                lane.edits.setCondition("FLG-"+field[0]+"-NOT-OK");
            }
            run(p,PARAGRAPHS.get(3));
        }
    }
    // Source 2986-3439 and CSSETATY: every bad/blank flag, phase and action; source engine is the oracle.
    @Test void everyEditFlagPreservesCursorColorBlankMarkerAndEarlyExit() throws Exception {
        for(var edit:AccountRenderState.Edit.values())for(String suffix:List.of("NOT-OK","BLANK"))
            for(String phase:List.of("CDEMO-PGM-ENTER","CDEMO-PGM-REENTER"))for(String action:ACTIONS) {
                String condition="FLG-"+edit.name().replace('_','-')+"-"+suffix;
                assertTrue(raw.path("conditions").has(condition),condition);
                var p=pair();for(var lane:p) {
                    clearFlags(lane.edits);lane.edits.setCondition(action);lane.edits.setCondition(phase);
                    lane.edits.setCondition(condition);
                }
                run(p,PARAGRAPHS.get(5));
            }
    }
    // Source 3013-3164: competing errors must honor the first source condition, not enum order.
    @Test void pairedBadFlagsPreserveCursorPriority() throws Exception {
        for(var first:AccountRenderState.Edit.values())for(var second:AccountRenderState.Edit.values()) {
            var p=pair();for(var lane:p) {
                clearFlags(lane.edits);
                lane.edits.setCondition("FLG-"+first.name().replace('_','-')+"-NOT-OK");
                lane.edits.setCondition("FLG-"+second.name().replace('_','-')+"-NOT-OK");
            }
            run(p,PARAGRAPHS.get(5));
        }
    }
    // Source 3010-3012 and 3169-3186: success/no-change overrides cursor errors; prior map resets color.
    @Test void statusCursorOverridesErrorsAndCardListRestoresDefaultColor() throws Exception {
        for(String info:List.of("FOUND-ACCOUNT-DATA","NO-CHANGES-DETECTED")) {
            var p=pair();for(var lane:p) {
                clearFlags(lane.edits);lane.edits.setCondition("FLG-ACCTFILTER-NOT-OK");
                lane.edits.setCondition("FLG-FIRST-NAME-NOT-OK");lane.edits.setCondition(info);
            }
            run(p,PARAGRAPHS.get(5));assertEquals("ACSTTUS",p[1].screen.cursor);
        }
        for(boolean cardList:new boolean[]{false,true}) {
            var p=pair();for(var lane:p) {
                clearFlags(lane.edits);lane.edits.put("ACCTSIDC","DFHRED");
                lane.edits.put("CDEMO-LAST-MAPSET",cardList?lane.edits.get("LIT-CCLISTMAPSET"):"OTHER");
            }
            run(p,PARAGRAPHS.get(5));
        }
    }
    // Source 3441-3564: standalone operations preserve attributes outside their own exact inventories.
    @Test void protectionKeepsCompleteScreenState() throws Exception {
        for(String paragraph:List.of(PARAGRAPHS.get(6),PARAGRAPHS.get(7))) {
            var p=pair();run(p,paragraph);run(p,paragraph);
        }
        var p=pair();run(p,PARAGRAPHS.get(6));run(p,PARAGRAPHS.get(7));
        for(String field:List.of("ACSTNUM","ACSCTRY","INFOMSG"))
            assertEquals(true,p[1].screen.attributes.get(field).get("protected"));
    }
    // Source 2955-2985 and 3566-3586: message ordering and intentionally untouched PF attributes.
    @Test void messageAndFunctionKeyStatesRetainAllSideEffects() throws Exception {
        for(String action:ACTIONS)for(String phase:List.of("CDEMO-PGM-ENTER","CDEMO-PGM-REENTER"))
            for(String info:List.of("","STALE INFO"))for(String error:List.of("","FIRST ERROR")) {
                var p=pair();for(var lane:p) {
                    lane.edits.setCondition(action);lane.edits.setCondition(phase);
                    lane.edits.put("WS-INFO-MSG",info);lane.edits.put("WS-RETURN-MSG",error);
                }
                run(p,PARAGRAPHS.get(4));run(p,PARAGRAPHS.get(8));
            }
    }
    @Test void oracleRejectsStorageScratchVisibleAndAttributeCorruption() throws Exception {
        var p=pair();same(p[0],p[1]);p[1].edits.put("WS-INPUT-FLAG","1");
        assertThrows(AssertionError.class,()->same(p[0],p[1]));
        var q=pair();var f=SourceEdits.class.getDeclaredField("values");f.setAccessible(true);
        @SuppressWarnings("unchecked") var values=(Map<String,String>)f.get(q[1].edits);values.put("mismatch","x");
        assertThrows(AssertionError.class,()->same(q[0],q[1]));
        var r=pair();r[1].screen.set("ACCTSID","DIFFERENT");assertThrows(AssertionError.class,()->same(r[0],r[1]));
        var s=pair();s[1].screen.attributes.get("ACCTSID").put("hidden",false);
        assertThrows(AssertionError.class,()->same(s[0],s[1]));
    }
}
