package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;

/** Supplemental CI oracle; expected values come from original statement execution. */
class AccountLocationRulesTest {
    private static JsonNode original,production;
    private static Set<String> states, prefixes;

    @BeforeAll static void load() throws Exception {
        JsonNode update=JsonMapper.builder().build().readTree(Path.of(System.getProperty("carddemo.root"),
            "work/carddemo-web-bindings/bindings.json").toFile()).path("account_update");
        ObjectNode copy=(ObjectNode)update.path("validation").deepCopy();
        copy.remove("native_paragraphs");
        ObjectNode paragraphs=(ObjectNode)copy.path("paragraphs");
        for(var entry:update.path("generic_edits").path("paragraphs").properties())
            paragraphs.set(entry.getKey(),entry.getValue());
        original=copy;
        production=AccountValidationModel.forProduction(update.path("validation"));
        states=literals("VALID-US-STATE-CODE");
        prefixes=literals("VALID-US-STATE-ZIP-CD2-COMBO");
    }

    private static Set<String> literals(String condition) {
        JsonNode data=original.path("conditions").path(condition);
        assertTrue(data.path("ranges").isEmpty());
        Set<String> values=new LinkedHashSet<>();
        for(JsonNode item:data.path("values")) {
            String literal=item.asText();
            assertTrue(literal.startsWith("'") && literal.endsWith("'"));
            values.add(literal.substring(1,literal.length()-1).replace("''","'"));
        }
        assertFalse(values.isEmpty());
        return Set.copyOf(values);
    }

    @Test void everyStateAndPrefixMatchesPinnedOriginalLookup() {
        Set<String> candidates=new LinkedHashSet<>(states);
        for(String prefix:prefixes)candidates.add(prefix.substring(0,2));
        candidates.addAll(Set.of("or","ZZ","  ","\0\0","O "," O"));
        for(String state:candidates) {
            var oracle=new SourceEdits(original);
            oracle.put("ACUP-NEW-CUST-ADDR-STATE-CD",state);
            oracle.run("1270-EDIT-US-STATE-CD");
            var result=AccountLocationRules.state(state,states);
            assertEquals(oracle.get("US-STATE-CODE-TO-EDIT"),result.scratch());
            assertEquals(!oracle.condition("INPUT-ERROR"),result.valid(),state);
            for(int prefix=0;prefix<100;prefix++) {
                String zip=String.format(Locale.ROOT,"%02d",prefix)+"ABC";
                var zipOracle=new SourceEdits(original);
                zipOracle.put("ACUP-NEW-CUST-ADDR-STATE-CD",state);
                zipOracle.put("ACUP-NEW-CUST-ADDR-ZIP",zip);
                zipOracle.run("1280-EDIT-US-STATE-ZIP-CD");
                var combination=AccountLocationRules.stateZip(state,zip,prefixes);
                assertEquals(zipOracle.get("US-STATE-AND-FIRST-ZIP2"),combination.scratch());
                assertEquals(!zipOracle.condition("INPUT-ERROR"),combination.valid(),state+zip);
            }
        }
    }

    @Test void noNormalizationOrFiveDigitPolicyIsIntroduced() {
        assertTrue(AccountLocationRules.state("OR",states).valid());
        assertFalse(AccountLocationRules.state("or",states).valid());
        assertTrue(AccountLocationRules.stateZip("OR","97ABC",prefixes).valid());
        assertEquals(AccountLocationRules.stateZip("OR","97000",prefixes),
                     AccountLocationRules.stateZip("OR","97\0  ",prefixes));
        assertFalse(AccountLocationRules.stateZip("OR","9 ABC",prefixes).valid());
        assertFalse(AccountLocationRules.stateZip("OR","  ABC",prefixes).valid());
        assertFalse(AccountLocationRules.stateZip("OR","\0\0ABC",prefixes).valid());
        // The two source lookup tables are independent: military prefixes are not states.
        assertFalse(AccountLocationRules.state("AA",states).valid());
        assertTrue(AccountLocationRules.stateZip("AA","34000",prefixes).valid());
    }

    @Test void productionSelectionRetiresOnlyLocationStatementsAndPreservesInput() {
        JsonNode before=original.deepCopy();
        JsonNode selected=AccountValidationModel.forProduction(original);
        assertEquals(before,original);
        for(String paragraph:Set.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD")) {
            assertFalse(selected.path("paragraphs").has(paragraph));
            assertEquals("AccountLocationRules",selected.path("native_paragraphs").path(paragraph).asText());
        }
        assertEquals(original.path("paragraphs").path("1275-EDIT-FICO-SCORE"),
                     selected.path("paragraphs").path("1275-EDIT-FICO-SCORE"));
    }

    private static void completeStorage(SourceEdits expected,SourceEdits actual) throws Exception {
        var storage=SourceEdits.class.getDeclaredField("storage");storage.setAccessible(true);
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        assertArrayEquals(((Commarea)storage.get(expected)).bytes(),((Commarea)storage.get(actual)).bytes());
        assertEquals(values.get(expected),values.get(actual));
    }

    @Test void rawStorageKeepsFirstErrorStaleFlagsAndScratch() throws Exception {
        int comparisons=0;
        for(String paragraph:Set.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD"))
            for(String state:new String[]{"OR","or","AA","ZZ","  ","\0\0"})
                for(String zip:new String[]{"97000","97ABC","34000","9 ABC","     ","\0\0ABC"})
                    for(String prior:new String[]{"","FIRST ERROR","\0"})
                        for(String inputFlag:new String[]{"0","1","\0"})
                            for(String stateFlag:new String[]{"\0","0","B"})
                                for(String zipFlag:new String[]{"\0","0","B"}) {
                                    var oracle=new SourceEdits(original);var candidate=new SourceEdits(production);
                                    for(var edits:new SourceEdits[]{oracle,candidate}) {
                                        edits.put("ACUP-NEW-CUST-ADDR-STATE-CD",state);
                                        edits.put("ACUP-NEW-CUST-ADDR-ZIP",zip);
                                        edits.put("WS-EDIT-VARIABLE-NAME","  State  ");
                                        edits.put("WS-RETURN-MSG",prior);
                                        edits.put("US-STATE-CODE-TO-EDIT","ZZ");
                                        edits.put("US-STATE-AND-FIRST-ZIP2","ZZ00");
                                        // Exercise transitions and stale flags independently (COACTUPC 2495-2507, 2542-2554).
                                        // Pinned storage bytes: COACTUPC 171-174 and 303-310.
                                        // The reduced model omits unreferenced 88-level names.
                                        edits.put("WS-INPUT-FLAG",inputFlag);
                                        edits.put("WS-EDIT-STATE-FLGS",stateFlag);
                                        edits.put("WS-EDIT-ZIPCODE-FLGS",zipFlag);
                                        assertEquals(inputFlag,edits.get("WS-INPUT-FLAG"));
                                        assertEquals(stateFlag,edits.get("WS-EDIT-STATE-FLGS"));
                                        assertEquals(zipFlag,edits.get("WS-EDIT-ZIPCODE-FLGS"));
                                        edits.run(paragraph);
                                    }
                                    completeStorage(oracle,candidate);
                                    comparisons++;
                                    assertEquals(oracle.condition("INPUT-ERROR"),candidate.condition("INPUT-ERROR"));
                                    assertTrue(candidate.trace().contains(new SourceEdits.Location("app/cbl/COACTUPC.cbl",
                                        paragraph.equals("1270-EDIT-US-STATE-CD")?2494:2537)));
                                }
        assertEquals(5832,comparisons);
    }

    @Test void storageOracleRejectsByteAndScratchMismatches() throws Exception {
        var oracle=new SourceEdits(original);var candidate=new SourceEdits(production);
        completeStorage(oracle,candidate);
        var storage=SourceEdits.class.getDeclaredField("storage");storage.setAccessible(true);
        var actual=(Commarea)storage.get(candidate);byte saved=actual.bytes()[0];
        actual.copyBytes(0,new byte[]{(byte)(saved ^ 1)});
        assertThrows(AssertionError.class,()->completeStorage(oracle,candidate));
        actual.copyBytes(0,new byte[]{saved});completeStorage(oracle,candidate);
        var values=SourceEdits.class.getDeclaredField("values");values.setAccessible(true);
        @SuppressWarnings("unchecked") var scratch=(Map<String,String>)values.get(candidate);
        scratch.put("fixture-only-mismatch","different");
        assertThrows(AssertionError.class,()->completeStorage(oracle,candidate));
    }

    @Test void selectionRejectsMalformedOrAlreadySelectedModelsWithoutMutatingInput() {
        assertThrows(IllegalArgumentException.class,()->AccountValidationModel.forProduction(null));
        var mapper=JsonMapper.builder().build();
        assertThrows(IllegalArgumentException.class,()->AccountValidationModel.forProduction(mapper.createObjectNode()));
        for(String paragraph:Set.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD")) {
            ObjectNode missing=(ObjectNode)original.deepCopy();
            ((ObjectNode)missing.path("paragraphs")).remove(paragraph);
            JsonNode before=missing.deepCopy();
            assertThrows(IllegalArgumentException.class,()->AccountValidationModel.forProduction(missing));
            assertEquals(before,missing);
        }
        ObjectNode malformed=(ObjectNode)original.deepCopy();malformed.put("native_paragraphs","bad");
        assertThrows(IllegalArgumentException.class,()->AccountValidationModel.forProduction(malformed));
        ObjectNode dual=(ObjectNode)original.deepCopy();
        dual.putObject("native_paragraphs").put("1270-EDIT-US-STATE-CD","OtherRule");
        JsonNode before=dual.deepCopy();
        assertThrows(IllegalArgumentException.class,()->AccountValidationModel.forProduction(dual));
        assertEquals(before,dual);
    }

    @Test void malformedParagraphBodiesAreNotSilentlyReplaced() {
        for(String paragraph:Set.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD"))
            for(String defect:Set.of("null","scalar","object","empty-array")) {
                ObjectNode invalid=(ObjectNode)original.deepCopy();
                ObjectNode paragraphs=(ObjectNode)invalid.path("paragraphs");
                switch(defect) {
                    case "null" -> paragraphs.putNull(paragraph);
                    case "scalar" -> paragraphs.put(paragraph,"bad");
                    case "object" -> paragraphs.putObject(paragraph);
                    case "empty-array" -> paragraphs.putArray(paragraph);
                    default -> throw new AssertionError(defect);
                }
                JsonNode before=invalid.deepCopy();
                var failure=assertThrows(IllegalArgumentException.class,
                    ()->AccountValidationModel.forProduction(invalid),paragraph+defect);
                assertEquals("location-paragraph-shape:"+paragraph,failure.getMessage());
                assertEquals(before,invalid);
            }
    }

    @Test void existingNativeOwnersAndSecondParagraphConflictsArePreserved() {
        ObjectNode source=(ObjectNode)original.deepCopy();
        source.putObject("native_paragraphs").put("fixture-unrelated","ExistingOwner");
        JsonNode before=source.deepCopy();
        JsonNode selected=AccountValidationModel.forProduction(source);
        assertEquals("ExistingOwner",selected.path("native_paragraphs").path("fixture-unrelated").asText());
        assertEquals(before,source);
        for(String paragraph:Set.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD")) {
            ObjectNode conflict=source.deepCopy();
            ((ObjectNode)conflict.path("native_paragraphs")).put(paragraph,"OtherOwner");
            JsonNode untouched=conflict.deepCopy();
            var failure=assertThrows(IllegalArgumentException.class,
                ()->AccountValidationModel.forProduction(conflict));
            assertEquals("location-already-native:"+paragraph,failure.getMessage());
            assertEquals(untouched,conflict);
        }
    }

    @Test void malformedLookupTablesFailClosed() {
        for(String condition:Set.of("VALID-US-STATE-CODE","VALID-US-STATE-ZIP-CD2-COMBO"))
            for(String defect:Set.of("missing","scalar","range","empty","unquoted","single-quote","numeric")) {
                ObjectNode invalid=(ObjectNode)production.deepCopy();
                ObjectNode conditions=(ObjectNode)invalid.path("conditions");
                ObjectNode data=(ObjectNode)conditions.path(condition);
                switch(defect) {
                    case "missing" -> conditions.remove(condition);
                    case "scalar" -> data.put("values","bad");
                    case "range" -> data.putArray("ranges").add("unsupported");
                    case "empty" -> data.putArray("values");
                    case "unquoted" -> data.putArray("values").add("OR");
                    case "single-quote" -> data.putArray("values").add("'");
                    case "numeric" -> data.putArray("values").add(42);
                    default -> throw new AssertionError(defect);
                }
                var candidate=new SourceEdits(invalid);
                String paragraph=condition.equals("VALID-US-STATE-CODE")
                    ? "1270-EDIT-US-STATE-CD" : "1280-EDIT-US-STATE-ZIP-CD";
                assertThrows(IllegalArgumentException.class,()->candidate.run(paragraph),condition+defect);
            }
    }
}
