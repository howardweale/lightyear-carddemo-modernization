package ai.lightyear.carddemo;

import java.util.*;
import tools.jackson.databind.JsonNode;

/** Rendering state keeps every field's value and attributes, including hidden fields. */
public final class ScreenFrame {
    public final String program;
    public final String transaction;
    public final JsonNode model;
    public final Map<String,String> values=new LinkedHashMap<>();
    public final Map<String,Map<String,Object>> attributes=new LinkedHashMap<>();
    public String message="";
    public String cursor="";
    public String endpoint="";
    public final List<SourceEdits.Location> trace=new ArrayList<>();
    public ScreenFrame(Bindings bindings,String program){this(bindings,program,bindings.clock);}
    public ScreenFrame(Bindings bindings,String program,java.time.Clock clock){
        this.program=program;JsonNode screen=bindings.screen(program);transaction=screen.path("transaction").asText();
        model=screen.path("model").path("maps").get(0);
        for(JsonNode f:model.path("fields")){
            String name=f.path("name").asText("");if(name.isEmpty())continue;
            values.put(name,pad(f.path("initial").asText(""),f.path("length").asInt()));
            Map<String,Object> a=new LinkedHashMap<>();a.put("protected",f.path("protected").asBoolean());a.put("hidden",f.path("hidden").asBoolean());
            a.put("color",f.path("color").asText());a.put("highlight",f.path("highlight").asText());
            a.put("basic",f.path("attributes"));a.put("modified",false);
            for(JsonNode attr:f.path("attributes"))if(attr.asText().equals("FSET"))a.put("modified",true);
            attributes.put(name,a);
            for(JsonNode attr:f.path("attributes"))if(attr.asText().equals("IC"))cursor=name;
        }
        headers(bindings,clock);
    }
    public void restore(SessionToken.Terminal terminal){
        if(terminal==null||!values.keySet().equals(terminal.values().keySet())||!attributes.keySet().equals(terminal.attributes().keySet()))throw new IllegalArgumentException("terminal-layout");
        for(var entry:terminal.values().entrySet()){
            if(entry.getValue()==null||entry.getValue().length()!=field(entry.getKey()).path("length").asInt())throw new IllegalArgumentException("terminal-field-length");
            Commarea.encode(entry.getValue());values.put(entry.getKey(),entry.getValue());
        }
        for(var entry:terminal.attributes().entrySet())attributes.put(entry.getKey(),new LinkedHashMap<>(entry.getValue()));
        cursor=terminal.cursor();message=terminal.message();endpoint=terminal.endpoint();
    }
    @CobolSource(program="COSGN00C", paragraph="POPULATE-HEADER-INFO", lines="177-208")
    private void headers(Bindings b,java.time.Clock clock){
        java.time.ZonedDateTime now=java.time.ZonedDateTime.now(clock);
        for(JsonNode h:b.program(program).path("headers")){
            String source=h.path("expression").asText(),value;
            if(source.startsWith("CCDA-TITLE"))value=b.root.path("common_constants").path(source).asText();
            else if(source.equals("WS-CURDATE-MM-DD-YY"))value=now.format(java.time.format.DateTimeFormatter.ofPattern("MM/dd/yy",Locale.ROOT));
            else if(source.equals("WS-CURTIME-HH-MM-SS"))value=now.format(java.time.format.DateTimeFormatter.ofPattern("HH:mm:ss",Locale.ROOT));
            else if(source.equals("LIT-THISPGM")||source.equals("WS-PGMNAME")||source.startsWith("WS-PGM-AUTH-"))value=program;
            else value=transaction;
            set(h.path("target").asText(),value);
        }
    }
    public JsonNode field(String name){for(JsonNode f:model.path("fields"))if(f.path("name").asText().equals(name))return f;throw new IllegalArgumentException("unknown-screen-field");}
    public void set(String name,String value){values.put(name,pad(value,field(name).path("length").asInt()));}
    public void error(String value,String cursor){message=value;set("ERRMSG",value);this.cursor=cursor;}
    public Map<String,String> receive(Map<String,String> input){
        Map<String,String> result=new LinkedHashMap<>();
        for(var entry:input.entrySet()){
            JsonNode field=field(entry.getKey());
            if(Boolean.TRUE.equals(attributes.get(entry.getKey()).get("protected")))throw new IllegalArgumentException("protected-field");
            if(entry.getValue()==null || entry.getValue().length()>field.path("length").asInt())throw new IllegalArgumentException("field-length");
            Commarea.encode(entry.getValue());
        }
        for(JsonNode f:model.path("fields")){
            String name=f.path("name").asText("");
            if(name.isEmpty() || Boolean.TRUE.equals(attributes.get(name).get("protected")))continue;
            result.put(name,pad(input.getOrDefault(name,""),f.path("length").asInt()));
        }
        return result;
    }
    static String pad(String value,int length){return value.length()>length?value.substring(0,length):value+" ".repeat(length-value.length());}
}
