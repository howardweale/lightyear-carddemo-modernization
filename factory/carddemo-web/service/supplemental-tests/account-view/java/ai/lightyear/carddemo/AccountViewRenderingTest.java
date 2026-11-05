package ai.lightyear.carddemo;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;

/** CI-only draft: original generated COBOL MOVE/STRING projection remains the independent oracle. */
class AccountViewRenderingTest {
    private static Bindings bindings;
    private static TypedRecords records;
    private static final Clock CLOCK=Clock.fixed(Instant.parse("2026-10-22T12:00:00Z"),ZoneOffset.UTC);
    @BeforeAll static void load() throws Exception {
        Path root=Path.of(System.getProperty("carddemo.root"));
        bindings=new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),
            root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build(),CLOCK);
        records=new TypedRecords(bindings);
    }
    private static ScreenFrame frame() {
        var result=new ScreenFrame(bindings,"COACTVWC",CLOCK);
        for(String field:result.values.keySet())result.set(field,"STALE-"+field);
        result.message="FIRST ERROR";result.cursor="ACCTSID";result.endpoint="unchanged";
        for(var attrs:result.attributes.values()) {
            attrs.put("protected",false);attrs.put("color","RED");attrs.put("hidden",true);
        }
        return result;
    }
    private static void same(ScreenFrame a,ScreenFrame b) {
        assertEquals(a.values,b.values);assertEquals(a.attributes,b.attributes);
        assertEquals(a.cursor,b.cursor);assertEquals(a.message,b.message);assertEquals(a.endpoint,b.endpoint);
        assertEquals(a.program,b.program);assertEquals(a.transaction,b.transaction);assertEquals(a.trace,b.trace);
    }
    private static Map<String,Object> copy(Map<String,Object> row) {
        if(row==null)return null;var result=new LinkedHashMap<String,Object>();
        row.forEach((key,value)->result.put(key,value instanceof byte[] bytes?bytes.clone():value));return result;
    }
    private static void unchanged(Map<String,Object> before,Map<String,Object> after) {
        if(before==null){assertNull(after);return;}assertEquals(before.keySet(),after.keySet());
        before.forEach((key,value)->{if(value instanceof byte[] bytes)assertArrayEquals(bytes,(byte[])after.get(key));
            else assertEquals(value,after.get(key));});
    }
    private static void compare(Map<String,Object> account,Map<String,Object> customer) {
        var beforeAccount=copy(account);var beforeCustomer=copy(customer);
        var old=frame();var typed=frame();Map<String,Map<String,Object>> rows=new LinkedHashMap<>();
        if(account!=null)rows.put("acctdata",account);if(customer!=null)rows.put("custdata",customer);
        new ScreenProjection(bindings).apply(old,bindings.root.path("account_view_projection"),rows);
        // The retained generic projection pads STRING like MOVE. Correct only that known
        // oracle defect using COACTVWC 496-504; all other generic results remain exact.
        // Independent original-COBOL fixtures below verify this receiving-byte behavior.
        if(customer!=null){
            assertEquals(12,old.values.get("ACSTSSN").length());
            assertEquals(" ",old.values.get("ACSTSSN").substring(11));
            old.set("ACSTSSN",old.values.get("ACSTSSN").substring(0,11)+typed.values.get("ACSTSSN").substring(11));
        }
        unchanged(beforeAccount,account);unchanged(beforeCustomer,customer);
        new AccountViewRendering(bindings).apply(typed,account,customer);
        same(old,typed);unchanged(beforeAccount,account);unchanged(beforeCustomer,customer);
    }
    private static void set(String table,Map<String,Object> row,String field,Object value) {
        var definition=bindings.field(table,field);String column=definition.path("column").asText();
        row.put(column+(definition.path("date").asBoolean()?"_raw":""),value);
    }
    // COACTVWC 471-523: missing rows preserve previous terminal fields; the service supplies the
    // initialized-account assumption when account is missing but customer was found.
    @Test void allRowPresenceCombinationsPreserveCompleteScreenAndRecordImages() {
        for(boolean account:new boolean[]{false,true})for(boolean customer:new boolean[]{false,true})
            compare(account?records.initialized("acctdata"):null,customer?records.initialized("custdata"):null);
        var customer=records.initialized("custdata");
        set("custdata",customer,"CUST-FIRST-NAME",Commarea.encode("Ada                      "));
        compare(records.initialized("acctdata"),customer);
    }
    // COACTVWC 473-523: vary every copied field independently so an omitted or misdirected MOVE differs.
    @Test void everySourceMovePreservesFixedWidthAndUntouchedFields() {
        String[] accountFields={"ACCT-ACTIVE-STATUS","ACCT-CURR-BAL","ACCT-CREDIT-LIMIT","ACCT-CASH-CREDIT-LIMIT",
            "ACCT-CURR-CYC-CREDIT","ACCT-CURR-CYC-DEBIT","ACCT-OPEN-DATE","ACCT-EXPIRAION-DATE","ACCT-REISSUE-DATE","ACCT-GROUP-ID"};
        String[] customerFields={"CUST-ID","CUST-FICO-CREDIT-SCORE","CUST-DOB-YYYY-MM-DD","CUST-FIRST-NAME",
            "CUST-MIDDLE-NAME","CUST-LAST-NAME","CUST-ADDR-LINE-1","CUST-ADDR-LINE-2","CUST-ADDR-LINE-3",
            "CUST-ADDR-STATE-CD","CUST-ADDR-ZIP","CUST-ADDR-COUNTRY-CD","CUST-PHONE-NUM-1","CUST-PHONE-NUM-2",
            "CUST-GOVT-ISSUED-ID","CUST-EFT-ACCOUNT-ID","CUST-PRI-CARD-HOLDER-IND"};
        for(String table:List.of("acctdata","custdata"))for(String field:table.equals("acctdata")?accountFields:customerFields)
            for(String variant:List.of("A","b"," ","0")) {
                var account=records.initialized("acctdata");var customer=records.initialized("custdata");
                var definition=bindings.field(table,field);Object value;
                if(definition.path("date").asBoolean())value=variant.equals(" ")?"          ":"2026-10-22";
                else if(definition.path("digits").asInt()>0)value=new BigDecimal(variant.equals("0")?"0":"123");
                else value=Commarea.encode(variant.repeat(definition.path("length").asInt()));
                set(table,table.equals("acctdata")?account:customer,field,value);compare(account,customer);
            }
    }
    // COACTVWC 475-486 and BMS output pictures: sign, zero suppression and each distinct money move.
    @Test void everyMoneyFieldKeepsSignMagnitudeAndEditedPicture() {
        for(String field:List.of("ACCT-CURR-BAL","ACCT-CREDIT-LIMIT","ACCT-CASH-CREDIT-LIMIT","ACCT-CURR-CYC-CREDIT","ACCT-CURR-CYC-DEBIT"))
            for(String value:List.of("0.00","0.01","-0.01","1234567.89","-1234567.89","999999999.99")) {
                var account=records.initialized("acctdata");set("acctdata",account,field,new BigDecimal(value));
                compare(account,records.initialized("custdata"));
            }
    }
    // COACTVWC 497-506: source reference modifications are 1:3, 4:2, 6:4 with literal hyphens.
    @Test void ssnSlicesPreserveLeadingZeroesAndRawDisplay() {
        for(String value:List.of("0","1","12345678","123456789","987654321")) {
            var customer=records.initialized("custdata");set("custdata",customer,"CUST-SSN",new BigDecimal(value));
            compare(records.initialized("acctdata"),customer);
        }
        var customer=records.initialized("custdata");set("custdata",customer,"CUST-SSN",Commarea.encode("ABC12DEFG"));
        compare(records.initialized("acctdata"),customer);
    }
    @Test void screenOracleDetectsValueAttributeAndMessageCorruption() {
        var a=frame();var b=frame();same(a,b);b.set("ACSTTUS","DIFFERENT");assertThrows(AssertionError.class,()->same(a,b));
        var c=frame();c.attributes.get("ACCTSID").put("hidden",false);assertThrows(AssertionError.class,()->same(a,c));
        var d=frame();d.message="CHANGED";assertThrows(AssertionError.class,()->same(a,d));
    }

    private record ReadFixture(java.sql.Connection db,List<String> trace,List<java.sql.PreparedStatement> statements,
                               List<Map<String,Object>> rows,List<Map<String,Object>> snapshots) {}
    private static ReadFixture database(List<Map<String,Object>> rows) throws Exception {
        var db=org.mockito.Mockito.mock(java.sql.Connection.class);var trace=new ArrayList<String>();
        var statements=new ArrayList<java.sql.PreparedStatement>();var snapshots=new ArrayList<Map<String,Object>>();
        for(var row:rows)snapshots.add(copy(row));
        org.mockito.Mockito.when(db.prepareStatement(org.mockito.ArgumentMatchers.anyString())).thenAnswer(call->{
            int index=statements.size();assertTrue(index<rows.size(),"Unexpected extra database read");
            String sql=call.getArgument(0);assertTrue(sql.startsWith("SELECT * FROM "),"Write attempted");trace.add(sql);
            var q=org.mockito.Mockito.mock(java.sql.PreparedStatement.class);statements.add(q);
            var rs=org.mockito.Mockito.mock(java.sql.ResultSet.class);var row=rows.get(index);
            org.mockito.Mockito.when(q.executeQuery()).thenReturn(rs);org.mockito.Mockito.when(rs.next()).thenReturn(row!=null,false);
            org.mockito.Mockito.doAnswer(key->{assertEquals(1,(int)key.getArgument(0));
                trace.add(HexFormat.of().formatHex((byte[])key.getArgument(1)));return null;
            }).when(q).setBytes(org.mockito.ArgumentMatchers.anyInt(),org.mockito.ArgumentMatchers.any(byte[].class));
            if(row!=null){var metadata=org.mockito.Mockito.mock(java.sql.ResultSetMetaData.class);
                org.mockito.Mockito.when(rs.getMetaData()).thenReturn(metadata);org.mockito.Mockito.when(metadata.getColumnCount()).thenReturn(row.size());
                int column=0;for(var item:row.entrySet()){column++;org.mockito.Mockito.when(metadata.getColumnName(column)).thenReturn(item.getKey());
                    org.mockito.Mockito.when(rs.getObject(column)).thenReturn(item.getValue());}}
            return q;
        });
        return new ReadFixture(db,trace,statements,rows,snapshots);
    }
    private static void readOnly(ReadFixture f,int expectedReads) throws Exception {
        assertEquals(expectedReads,f.statements.size());
        org.mockito.Mockito.verify(f.db,org.mockito.Mockito.times(expectedReads)).prepareStatement(org.mockito.ArgumentMatchers.anyString());
        org.mockito.Mockito.verifyNoMoreInteractions(f.db);
        for(var q:f.statements){org.mockito.Mockito.verify(q).setBytes(org.mockito.ArgumentMatchers.eq(1),org.mockito.ArgumentMatchers.any(byte[].class));
            org.mockito.Mockito.verify(q).executeQuery();org.mockito.Mockito.verify(q).close();org.mockito.Mockito.verifyNoMoreInteractions(q);}
        for(int i=0;i<f.rows.size();i++)unchanged(f.snapshots.get(i),f.rows.get(i));
    }
    private static Map<String,Object> crossReference() {
        var row=records.initialized("cardxref");
        for(var item:Map.of("XREF-ACCT-ID","00000000050","XREF-CUST-ID","123456789","XREF-CARD-NUM","1234567890123456").entrySet()){
            var field=bindings.field("cardxref",item.getKey());
            set("cardxref",row,item.getKey(),field.path("digits").asInt()>0?new BigDecimal(item.getValue()):Commarea.encode(item.getValue()));
        }return row;
    }
    private static void compareService(String aid,String account,List<Map<String,Object>> rows,int reads,String previous) throws Exception {
        var leftRows=new ArrayList<Map<String,Object>>();var rightRows=new ArrayList<Map<String,Object>>();
        for(var row:rows){leftRows.add(copy(row));rightRows.add(copy(row));}
        var left=database(leftRows);var right=database(rightRows);
        var a=new Commarea(bindings.root.path("program_commareas").path("COACTVWC"),null);
        a.set("CDEMO-FROM-PROGRAM",previous);a.set("CDEMO-FROM-TRANID",previous.isBlank()?"    ":"CM00");
        a.set("CDEMO-ACCT-ID","98765432101");a.set("CDEMO-CUST-ID","987654321");a.set("CDEMO-CARD-NUM","9876543210987654");
        var b=new Commarea(bindings.root.path("program_commareas").path("COACTVWC"),a.bytes());
        var input=Map.of("ACCTSID",account);var old=new AccountViewProjectionOracle(bindings).interact(left.db,a,aid,input);
        var typed=new AccountViewService(bindings).interact(right.db,b,aid,input);
        same(old.screen(),typed.screen());assertEquals(old.nextProgram(),typed.nextProgram());assertEquals(old.ended(),typed.ended());
        assertArrayEquals(a.bytes(),b.bytes());assertEquals(left.trace,right.trace);readOnly(left,reads);readOnly(right,reads);
        if(reads>0){assertTrue(left.trace.get(0).contains("\"cardxref\""));assertTrue(left.trace.get(0).contains("ebcdic_key_aix_"));
            assertEquals(HexFormat.of().formatHex(Commarea.encode(account)),left.trace.get(1));}
        if(reads==3){assertTrue(left.trace.get(2).contains("\"acctdata\""));assertTrue(left.trace.get(4).contains("\"custdata\""));
            assertEquals(HexFormat.of().formatHex(Commarea.encode(account)),left.trace.get(3));
            assertEquals(HexFormat.of().formatHex(Commarea.encode("123456789")),left.trace.get(5));}
    }
    // COACTVWC 306-350, 581, 628-679: PF3 returns, initial entry and invalid inputs cannot read or write records.
    @Test void serviceNoReadRoutesPreserveEveryCommareaByteAndScreenField() throws Exception {
        for(String previous:List.of("        ","COMEN01C")){
            compareService("INITIAL","",List.of(),0,previous);compareService("PF3","00000000050",List.of(),0,previous);
            for(String aid:List.of("ENTER","PF7"))for(String value:List.of("","*","00000000000","1234","abcdefghijk"))
                compareService(aid,value,List.of(),0,previous);
        }
    }
    // COACTVWC 687-868: cross-reference first; missing account still reads customer and preserves the first error.
    @Test void serviceReadRoutesPreserveCompleteStateOrderAndImmutableDatabaseRows() throws Exception {
        for(String aid:List.of("ENTER","PF7")){
            compareService(aid,"00000000050",Arrays.asList((Map<String,Object>)null),1,"COMEN01C");
            for(int missing=0;missing<4;missing++){
                var account=records.initialized("acctdata");var customer=records.initialized("custdata");
                set("acctdata",account,"ACCT-CURR-BAL",new BigDecimal("-1234567.89"));
                set("custdata",customer,"CUST-FIRST-NAME",Commarea.encode("Ada                      "));
                set("custdata",customer,"CUST-SSN",new BigDecimal("12345678"));
                compareService(aid,"00000000050",Arrays.asList(crossReference(),(missing&1)==0?account:null,(missing&2)==0?customer:null),3,"COMEN01C");
            }
        }
    }

    // Original COACTVWC 471-523 is executed independently in CI, with full reference storage retained.
    @Test void originalCobolProjectionFixturesMatchCompleteFramesAndPreserveRows() throws Exception {
        Path root=Path.of(System.getProperty("carddemo.root"));
        var document=JsonMapper.builder().build().readTree(java.nio.file.Files.readString(root.resolve("work/carddemo-account-view/source-fixtures.json")));
        assertEquals("carddemo-view-source-fixtures/1",document.path("schema").asText());
        assertTrue(document.path("projection_only").asBoolean());assertFalse(document.path("whole_storage_java_equivalence").asBoolean(true));
        String source=java.nio.file.Files.readString(root.resolve("spec/modernization/carddemo-screens/upstream/app/cbl/COACTVWC.cbl")).replace("\r\n","\n");
        assertEquals(HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(source.getBytes(java.nio.charset.StandardCharsets.UTF_8))),document.path("source_sha256").asText());
        assertTrue(document.path("source_bindings").has("src/lightyear_data/carddemo/reference_screens.py"));
        assertTrue(document.path("source_bindings").has("tools/carddemo_account_view_fixtures.py"));
        for(var property:document.path("source_bindings").properties()) {
            Path sourceFile=root.resolve(property.getKey()).normalize();assertTrue(sourceFile.startsWith(root.normalize()));
            assertEquals(HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(java.nio.file.Files.readAllBytes(sourceFile))),property.getValue().asText());
        }
        assertEquals(93,document.path("case_count").asInt());assertEquals(93,document.path("cases").size());
        var identities=new HashSet<String>();
        for(var item:document.path("cases")) {
            assertTrue(identities.add(item.path("id").asText()));assertFalse(item.path("statement_trace").isEmpty());
            assertTrue(item.path("reference_before").size()>0);assertEquals(item.path("reference_before").size(),item.path("reference_after").size());
            Map<String,Object> account=item.path("account").isNull()?null:TypedRecordImage.project(bindings.mapping("acctdata"),HexFormat.of().parseHex(item.path("account").asText())).columns();
            Map<String,Object> customer=item.path("customer").isNull()?null:TypedRecordImage.project(bindings.mapping("custdata"),HexFormat.of().parseHex(item.path("customer").asText())).columns();
            var beforeAccount=copy(account);var beforeCustomer=copy(customer);var expected=frame();var typed=frame();
            assertEquals(28,item.path("expected").size());
            for(var property:item.path("expected").properties())expected.set(property.getKey(),property.getValue().asText());
            new AccountViewRendering(bindings).apply(typed,account,customer);
            same(expected,typed);unchanged(beforeAccount,account);unchanged(beforeCustomer,customer);
        }
    }

    // COACTVWC 493-504: STRING does not clear its receiver, and absent customers do not write it.
    @Test void ssnStringPreservesReceivingTailAcrossRepeatedWritesAndMissingCustomer() {
        for(String tail:List.of(" ","S","0","!","\u0000")) {
            var typed=frame();typed.set("ACSTSSN","ABCDEFGHIJK"+tail);var expected=frame();
            expected.set("ACSTSSN","ABCDEFGHIJK"+tail);
            new AccountViewRendering(bindings).apply(typed,null,null);same(expected,typed);
            var customer=records.initialized("custdata");var before=copy(customer);
            new AccountViewRendering(bindings).apply(typed,null,customer);
            assertEquals("000-00-0000"+tail,typed.values.get("ACSTSSN"));unchanged(before,customer);
            set("custdata",customer,"CUST-SSN",Commarea.encode("ABC12DEFG"));before=copy(customer);
            new AccountViewRendering(bindings).apply(typed,null,customer);
            assertEquals("ABC-12-DEFG"+tail,typed.values.get("ACSTSSN"));unchanged(before,customer);
            var snapshot=new LinkedHashMap<>(typed.values);
            new AccountViewRendering(bindings).apply(typed,null,null);assertEquals(snapshot,typed.values);
        }
    }

    // COACTVWC 324-350,581,653-679: identical field resolution and MOVE/SET bytes.
    @Test void typedCommonAreaDelegatesEveryFieldWithoutChangingStorage() {
        String[] names={"CDEMO-FROM-PROGRAM","CDEMO-FROM-TRANID","CDEMO-TO-PROGRAM","CDEMO-TO-TRANID","CDEMO-USER-TYPE","CDEMO-PGM-CONTEXT","CDEMO-LAST-MAPSET","CDEMO-LAST-MAP","CDEMO-ACCT-ID","CDEMO-CUST-ID","CDEMO-CARD-NUM"};
        var layout=bindings.root.path("program_commareas").path("COACTVWC");
        CommonArea.validateLayout(layout);
        assertEquals(names.length,CommonArea.Field.values().length);
        for(int i=0;i<names.length;i++)for(String value:List.of("0","1")) {
            var left=new Commarea(layout,null);var right=new Commarea(layout,left.bytes());var typed=new CommonArea(right);
            var field=CommonArea.Field.values()[i];left.set(names[i],value);typed.set(field,value);
            assertArrayEquals(left.bytes(),right.bytes());assertEquals(left.get(names[i]),typed.get(field));
            left.move(names[i],value);typed.move(field,value);assertArrayEquals(left.bytes(),right.bytes());
        }
        var left=new Commarea(layout,null);var right=new Commarea(layout,left.bytes());var typed=new CommonArea(right);
        left.move("CDEMO-LAST-MAP","ABCDEFGHIJK");typed.move(CommonArea.Field.LAST_MAP,"ABCDEFGHIJK");
        assertArrayEquals(left.bytes(),right.bytes());
        assertThrows(IllegalArgumentException.class,()->typed.set(CommonArea.Field.PROGRAM_CONTEXT,"not-a-number"));
        assertThrows(NullPointerException.class,()->new CommonArea(null));
    }
    // Startup-only invalid binding fixtures: refusal precedes every interact call.
    @Test void unknownAndAmbiguousCommonFieldsRefuseAtServiceConstruction() throws Exception {
        var json=JsonMapper.builder().build();
        String source=bindings.root.toString();
        var layout=bindings.root.path("program_commareas").path("COACTVWC");
        assertThrows(IllegalArgumentException.class,()->Commarea.requireFields(layout,"CDEMO-DOES-NOT-EXIST"));
        var broken=(tools.jackson.databind.node.ObjectNode)json.readTree(source);
        var fields=(tools.jackson.databind.node.ArrayNode)broken.path("program_commareas").path("COACTVWC").path("fields");
        for(int i=0;i<fields.size();i++)if(fields.get(i).path("path").asText().endsWith(".CDEMO-ACCT-ID")) {
            ((tools.jackson.databind.node.ObjectNode)fields.get(i)).put("path","UNKNOWN-FIELD");break;
        }
        assertThrows(IllegalArgumentException.class,()->CommonArea.validateLayout(broken.path("program_commareas").path("COACTVWC")));
        var duplicate=(tools.jackson.databind.node.ObjectNode)json.readTree(layout.toString());
        var copy=(tools.jackson.databind.node.ArrayNode)duplicate.path("fields");
        for(var field:layout.path("fields"))if(field.path("path").asText().endsWith(".CDEMO-ACCT-ID")){copy.add(field.deepCopy());break;}
        assertThrows(IllegalArgumentException.class,()->CommonArea.validateLayout(duplicate));
        java.nio.file.Path temporary=java.nio.file.Files.createTempDirectory("common-area-bindings-");
        try {
            var bind=temporary.resolve("bindings.json");var plan=temporary.resolve("plan.json");
            java.nio.file.Files.writeString(bind,broken.toString());java.nio.file.Files.writeString(plan,bindings.data.toString());
            var invalid=new Bindings(bind,plan,json,CLOCK);
            assertThrows(IllegalArgumentException.class,()->new AccountViewService(invalid));
        } finally {
            java.nio.file.Files.deleteIfExists(temporary.resolve("bindings.json"));java.nio.file.Files.deleteIfExists(temporary.resolve("plan.json"));java.nio.file.Files.delete(temporary);
        }
    }
    // COACTVWC source constants used by 324-350: load once, reject malformed startup data.
    @Test void typedConstantsAreValidatedOnceAndKeepExactSourceText() throws Exception {
        var values=bindings.program("COACTVWC").path("constants");var constants=AccountViewConstants.load(bindings);
        assertEquals(values.path("LIT-MENUPGM").asText(),constants.menuProgram());
        assertEquals(values.path("LIT-MENUTRANID").asText(),constants.menuTransaction());
        assertEquals(values.path("LIT-THISMAPSET").asText(),constants.mapset());
        assertEquals(values.path("LIT-THISMAP").asText(),constants.map());
        var mutable=(tools.jackson.databind.node.ObjectNode)values;
        var saved=mutable.path("LIT-MENUPGM").deepCopy();
        try {
            mutable.remove("LIT-MENUPGM");assertThrows(IllegalArgumentException.class,()->new AccountViewService(bindings));
            mutable.put("LIT-MENUPGM",12);assertThrows(IllegalArgumentException.class,()->new AccountViewService(bindings));
            mutable.put("LIT-MENUPGM","");assertThrows(IllegalArgumentException.class,()->new AccountViewService(bindings));
            assertEquals(saved.asText(),constants.menuProgram());
        } finally {mutable.set("LIT-MENUPGM",saved);}
    }
}
