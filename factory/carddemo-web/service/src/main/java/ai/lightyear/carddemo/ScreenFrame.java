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
    public ScreenFrame(Bindings bindings,String program){
        this.program=program;JsonNode screen=bindings.screen(program);transaction=screen.path("transaction").asText();
        model=screen.path("model").path("maps").get(0);
        for(JsonNode f:model.path("fields")){
            String name=f.path("name").asText("");if(name.isEmpty())continue;
            values.put(name,pad(f.path("initial").asText(""),f.path("length").asInt()));
            Map<String,Object> a=new LinkedHashMap<>();a.put("protected",f.path("protected").asBoolean());a.put("hidden",f.path("hidden").asBoolean());
            a.put("color",f.path("color").asText());a.put("highlight",f.path("highlight").asText());
            attributes.put(name,a);
            for(JsonNode attr:f.path("attributes"))if(attr.asText().equals("IC"))cursor=name;
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
