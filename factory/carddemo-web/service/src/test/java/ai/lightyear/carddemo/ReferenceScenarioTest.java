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
    List<String> multiset(List<?> values){return values.stream().map(json::writeValueAsString).sorted().toList();}
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
            var engine=new InteractionEngine(b,new SessionToken(new byte[32],b.hash,clock,json),ds,Map.of(
                "COSGN00C",new SignonService(b),"COMEN01C",new MenuService(b),"COACTVWC",new AccountViewService(b),
                "COACTUPC",new AccountUpdateService(b),"COPAUS0C",new AuthorizationListService(b),"COPAUS1C",new AuthorizationDetailService(b)));
            Map<Integer,String> tokens=new HashMap<>();Set<String> seen=new HashSet<>();
            try{for(JsonNode row:cases){
                int session=row.path("session").asInt();Map<String,String> fields=new HashMap<>();for(String key:row.path("fields").propertyNames())fields.put(key,row.path("fields").path(key).asText());
                var response=engine.interact(new InteractionEngine.Request(tokens.get(session),row.path("aid").asText(),fields));tokens.put(session,response.token());
                JsonNode expected=row.path("expected"),screen=json.valueToTree(response.screen());seen.add(response.screen().program);
                assertEquals(expected.path("program").asText(),response.screen().program);assertEquals(expected.path("ended").asBoolean(),response.ended());
                assertEquals(expected.path("screen").path("message").asText(),response.screen().message);
                if(!row.path("terminal_text_only").asBoolean()){
                    for(String part:List.of("values","cursor"))assertEquals(expected.path("screen").path(part),screen.path(part),row.path("case").asText()+" "+part);
                    assertEquals(attrs(expected.path("screen").path("attributes")),attrs(screen.path("attributes")));
                }
                var observed=state(actual);assertEquals(new TreeSet<>(row.path("database").propertyNames()),observed.keySet());
                for(String table:observed.keySet()){
                    List<Object> wanted=new ArrayList<>();for(JsonNode item:row.path("database").path(table))wanted.add(canonical(item));
                    assertEquals(multiset(wanted),multiset(observed.get(table)),row.path("case").asText()+" "+table);
                }
            }assertEquals(Set.of("COSGN00C","COMEN01C","COACTVWC","COACTUPC","COPAUS0C","COPAUS1C"),seen);
            }finally{actual.rollback();}
        }
    }
}
