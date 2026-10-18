package ai.lightyear.carddemo;

import java.nio.file.*;
import java.sql.*;
import java.time.*;
import java.math.BigDecimal;
import java.util.*;
import java.lang.reflect.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** CI-only replay of independently interpreted COBOL, with a real disposable PostgreSQL DB.
 * Each mutant receives the identical fixture. A connection wrapper rolls back the whole
 * replay; separate InteractionEngine tests verify actual commit/rollback invocation.
 */
@EnabledIfSystemProperty(named="carddemo.proof",matches="true")
class ReferenceScenarioTest {
    final JsonMapper json=JsonMapper.builder().build();
    Object canonical(JsonNode n){
        if(n.isNumber())return Map.of("$number",new BigDecimal(n.asText()).stripTrailingZeros().toPlainString());
        if(n.isObject()){Map<String,Object> result=new TreeMap<>();for(String key:n.propertyNames())result.put(key,canonical(n.path(key)));return result;}
        if(n.isArray()){List<Object> result=new ArrayList<>();for(JsonNode v:n)result.add(canonical(v));return result;}
        if(n.isNull())return null;if(n.isBoolean())return n.asBoolean();return n.asText();
    }
    Object attrs(JsonNode n){
        Map<String,Object> result=new TreeMap<>();
        for(String key:n.propertyNames()){
            JsonNode a=n.path(key);Map<String,Object> value=new TreeMap<>();for(String p:a.propertyNames())value.put(p,canonical(a.path(p)));
            boolean bright=false,autoskip=false;for(JsonNode b:a.path("basic")){bright|=b.asText().equals("BRT");autoskip|=b.asText().equals("ASKIP");}
            value.putIfAbsent("intensity",bright?"BRIGHT":a.path("hidden").asBoolean()?"DARK":"NORMAL");value.putIfAbsent("autoskip",autoskip);result.put(key,value);
        }return result;
    }
    Map<String,List<Object>> state(Connection c)throws Exception{
        Map<String,List<Object>> result=new TreeMap<>();List<String> tables=new ArrayList<>();
        try(var s=c.createStatement();var q=s.executeQuery("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")){while(q.next())tables.add(q.getString(1));}
        assertFalse(tables.isEmpty());
        for(String table:tables){assertTrue(table.matches("[a-z][a-z0-9_]*"));List<Object> rows=new ArrayList<>();
            try(var s=c.createStatement();var q=s.executeQuery("SELECT to_jsonb(t)::text FROM "+table+" t")){while(q.next())rows.add(canonical(json.readTree(q.getString(1))));}result.put(table,rows);
        }return result;
    }
    JsonNode expectedDatabase(JsonNode row)throws Exception{
        JsonNode ref=row.path("database_file");String hash=ref.path("sha256").asText();
        assertTrue(hash.matches("[0-9a-f]{64}"));assertEquals("expected-database/"+hash+".json",ref.path("path").asText());
        Path parent=Path.of(System.getProperty("carddemo.cases")).toAbsolutePath().getParent();
        byte[] bytes=Files.readAllBytes(parent.resolve(ref.path("path").asText()));
        assertEquals(hash,HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes)));
        return json.readTree(bytes);
    }
    List<String> multiset(List<?> values){return values.stream().map(json::writeValueAsString).sorted().toList();}
    @Test void keyedAuthorizationPagesIgnoreInsertionOrderAndStayWithinParent()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        Bindings b=new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),json,Clock.systemUTC());
        var records=new AuthorizationRecords(b);var typed=new TypedRecords(b);
        try(Connection db=DriverManager.getConnection("jdbc:postgresql://127.0.0.1:5432/carddemo","carddemo","disposable-public-demo")){
            // Seed inserts identifiers 1..7, but their DBD sequence keys decrease.
            var parent=records.summary(db,"00000000050");assertNotNull(parent);
            var first=records.page(db,parent,null,false,5);
            assertEquals(List.of("7","6","5","4","3"),first.stream().map(r->typed.text("pautdtl1",r,"PA-TRANSACTION-ID").stripTrailing()).toList());
            byte[] boundary=AuthorizationRecords.key(first.get(4));
            var next=records.page(db,parent,boundary,false,5);
            assertEquals(List.of("2","1"),next.stream().map(r->typed.text("pautdtl1",r,"PA-TRANSACTION-ID").stripTrailing()).toList());
            var inclusive=records.page(db,parent,boundary,true,5);
            assertEquals(List.of("3","2","1"),inclusive.stream().map(r->typed.text("pautdtl1",r,"PA-TRANSACTION-ID").stripTrailing()).toList());
            assertTrue(records.page(db,parent,AuthorizationRecords.key(next.get(1)),false,5).isEmpty());
            var other=new HashMap<String,Object>(parent);other.put("path_key",new byte[]{0});
            assertTrue(records.page(db,other,null,false,5).isEmpty());
            assertTrue(records.page(db,other,boundary,true,5).isEmpty());
        }
    }
    @Test void everyRawReferenceInteractionMatchesAllFieldsAttributesCursorMessageAndDatabase()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));Clock clock=Clock.fixed(Instant.parse("2026-10-17T12:34:56Z"),ZoneOffset.UTC);
        Bindings b=new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),json,clock);
        JsonNode cases=json.readTree(Files.readString(Path.of(System.getProperty("carddemo.cases"))));assertTrue(cases.size()>0);
        try(Connection actual=DriverManager.getConnection("jdbc:postgresql://127.0.0.1:5432/carddemo","carddemo","disposable-public-demo")){
            actual.setAutoCommit(false);
            Connection wrapped=(Connection)Proxy.newProxyInstance(Connection.class.getClassLoader(),new Class[]{Connection.class},(proxy,method,args)->{
                if(Set.of("commit","close").contains(method.getName()))return null;
                if(method.getName().equals("setAutoCommit")){assertEquals(false,args[0]);return null;}
                try{return method.invoke(actual,args);}catch(InvocationTargetException e){throw e.getCause();}
            });
            DataSource ds=mock(DataSource.class);when(ds.getConnection()).thenReturn(wrapped);
            var tokenCodec=new SessionToken(new byte[32],b.hash,clock,json);
            var engine=new InteractionEngine(b,tokenCodec,ds,Map.of(
                "COSGN00C",new SignonService(b),"COMEN01C",new MenuService(b),"COACTVWC",new AccountViewService(b),
                "COACTUPC",new AccountUpdateService(b),"COPAUS0C",new AuthorizationListService(b),"COPAUS1C",new AuthorizationDetailService(b)));
            Map<Integer,String> tokens=new HashMap<>();Set<String> seen=new HashSet<>();
            try{for(JsonNode row:cases){
                int session=row.path("session").asInt();Map<String,String> fields=new HashMap<>();for(String key:row.path("fields").propertyNames())fields.put(key,row.path("fields").path(key).asText());
                var response=engine.interact(new InteractionEngine.Request(tokens.get(session),row.path("aid").asText(),fields));tokens.put(session,response.token());
                JsonNode expected=row.path("expected"),screen=json.valueToTree(response.screen());seen.add(response.screen().program);
                assertEquals(expected.path("program").asText(),response.screen().program);assertEquals(expected.path("ended").asBoolean(),response.ended());
                if(row.path("navigation_boundary_only").asBoolean())assertEquals("/not-in-this-slice",response.screen().endpoint);
                else assertEquals(expected.path("screen").path("message").asText(),response.screen().message);
                if(!row.path("terminal_text_only").asBoolean()&&!row.path("navigation_boundary_only").asBoolean()){
                    for(String part:List.of("values","cursor"))assertEquals(expected.path("screen").path(part),screen.path(part),row.path("case").asText()+" "+part);
                    assertEquals(attrs(expected.path("screen").path("attributes")),attrs(screen.path("attributes")));
                }
                // Compare raw returned state, including routing and private tails.
                // A source fault has no proved RETURN; SEND TEXT has no token.
                if(!response.ended()&&!expected.has("source_fault")){
                    var returned=tokenCodec.verify(response.token());
                    assertEquals(expected.path("program").asText(),returned.program());
                    assertArrayEquals(HexFormat.of().parseHex(expected.path("commarea").asText()),
                        Base64.getDecoder().decode(returned.commarea()),row.path("case").asText()+" returned COMMAREA");
                }
                JsonNode expectedState=expectedDatabase(row);var observed=state(actual);assertEquals(new TreeSet<>(expectedState.propertyNames()),observed.keySet());
                for(String table:observed.keySet()){
                    List<Object> wanted=new ArrayList<>();for(JsonNode item:expectedState.path(table))wanted.add(canonical(item));
                    assertEquals(multiset(wanted),multiset(observed.get(table)),row.path("case").asText()+" "+table);
                }
            }assertEquals(Set.of("COSGN00C","COMEN01C","COACTVWC","COACTUPC","COPAUS0C","COPAUS1C"),seen);
            }finally{actual.rollback();}
        }
    }
}
