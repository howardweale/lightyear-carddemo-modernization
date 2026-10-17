package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** Bounded Java execution of fully parsed source edit statements.
 * Per-interaction scratch storage; never a session, database or reference oracle.
 */
public final class SourceEdits {
    private final JsonNode model;
    private final Map<String,String> values=new LinkedHashMap<>();
    private final List<Location> trace=new ArrayList<>();private int steps;
    public record Location(String source,int line){}
    private record Value(String text,boolean numeric,boolean figurative){}
    public SourceEdits(JsonNode model){
        this.model=model;
        for(var entry:model.path("fields").properties())values.put(entry.getKey(),entry.getValue().path("initial").asText());
        setCondition("INPUT-OK");setCondition("WS-RETURN-MSG-OFF");
    }
    private JsonNode field(String name){JsonNode f=model.path("fields").path(name);if(f.isMissingNode())throw new IllegalArgumentException("edit-field:"+name);return f;}
    public String get(String name){field(name);return values.get(name);}
    public void put(String name,String value){JsonNode f=field(name);
        if(f.path("type").asText().equals("number")){
            BigDecimal number=new BigDecimal(value);if(number.scale()>0&&number.stripTrailingZeros().scale()>0)throw new IllegalArgumentException("edit-integral-field");
            values.put(name,number.toBigIntegerExact().toString());
        }else {int n=f.path("length").asInt();Commarea.encode(value);values.put(name,(value+" ".repeat(n)).substring(0,n));}
    }
    public List<Location> trace(){return List.copyOf(trace);}
    private void visit(JsonNode node){if(++steps>10000)throw new IllegalStateException("edit-step-limit");trace.add(new Location(node.path("source").asText(),node.path("line").asInt()));}
    private static String trimSpaces(String value){int a=0,b=value.length();while(a<b&&value.charAt(a)==' ')a++;while(b>a&&value.charAt(b-1)==' ')b--;return value.substring(a,b);}
    private static String figurative(String token,int length){
        if(token.startsWith("LOW-VALUE"))return "\u0000".repeat(length);
        if(token.startsWith("SPACE"))return " ".repeat(length);
        if(token.startsWith("ZERO"))return "0".repeat(length);
        throw new IllegalArgumentException("edit-figurative");
    }
    private String conditionValue(String token,String name){
        if(token.startsWith("'"))return token.substring(1,token.length()-1).replace("''","'");
        return token.matches("[0-9]+")?token:figurative(token,field(name).path("length").asInt());
    }
    public boolean condition(String name){JsonNode condition=model.path("conditions").path(name);
        if(condition.isMissingNode())throw new IllegalArgumentException("edit-condition:"+name);
        String parent=condition.path("parent").asText();String actual=get(parent);
        for(JsonNode v:condition.path("values"))if(paddedEqual(actual,conditionValue(v.asText(),parent)))return true;
        return false;
    }
    private void setCondition(String name){JsonNode c=model.path("conditions").path(name);
        if(c.isMissingNode())throw new IllegalArgumentException("edit-condition:"+name);
        String parent=c.path("parent").asText();put(parent,conditionValue(c.path("values").get(0).asText(),parent));
    }
    private static boolean paddedEqual(String a,String b){int n=Math.max(a.length(),b.length());return (a+" ".repeat(n-a.length())).equals(b+" ".repeat(n-b.length()));}
    private Value evaluate(JsonNode e){visit(e);String op=e.path("op").asText();
        switch(op){
            case "literal":return new Value(e.path("value").asText(),false,false);
            case "number":return new Value(e.path("value").asText(),true,false);
            case "figurative":return new Value(e.path("value").asText(),false,true);
            case "field":{String n=e.path("name").asText();return new Value(get(n),field(n).path("type").asText().equals("number"),false);}
            case "slice":{String text=evaluate(e.path("operand")).text();int a=integer(e.path("start"))-1,n=integer(e.path("length"));
                if(a<0||n<1||a+n>text.length())throw new IllegalArgumentException("edit-reference-modification");return new Value(text.substring(a,a+n),false,false);}
            case "TRIM":return new Value(trimSpaces(evaluate(e.path("operand")).text()),false,false);
            case "LENGTH":return new Value(Integer.toString(evaluate(e.path("operand")).text().length()),true,false);
            case "NUMVAL":{String text=trimSpaces(evaluate(e.path("operand")).text());
                // This bounded intrinsic is emitted only after IS NUMERIC in the
                // selected paragraphs. Broader NUMVAL/NUMVAL-C need their own proof.
                if(!text.matches("[0-9]+"))throw new IllegalArgumentException("edit-numval-outside-proved-subset");
                return new Value(new BigDecimal(text).toPlainString(),true,false);}
            default:throw new IllegalArgumentException("edit-expression:"+op);
        }
    }
    private int integer(JsonNode e){return new BigDecimal(evaluate(e).text()).intValueExact();}
    private boolean test(JsonNode e){visit(e);switch(e.path("op").asText()){
        case "or":return test(e.path("left"))||test(e.path("right"));
        case "and":return test(e.path("left"))&&test(e.path("right"));
        case "not":return !test(e.path("operand"));
        case "condition":return condition(e.path("name").asText());
        case "numeric":return evaluate(e.path("operand")).text().matches("[0-9]+");
        case "compare":{
            Value a=evaluate(e.path("left")),b=evaluate(e.path("right"));
            String left=a.figurative()?figurative(a.text(),b.text().length()):a.text();
            String right=b.figurative()?figurative(b.text(),left.length()):b.text();int comparison;
            if(a.numeric()||b.numeric())comparison=new BigDecimal(left).compareTo(new BigDecimal(right));
            else{int n=Math.max(left.length(),right.length());comparison=Arrays.compareUnsigned(Commarea.encode(left+" ".repeat(n-left.length())),Commarea.encode(right+" ".repeat(n-right.length())));}
            return switch(e.path("operator").asText()){case "EQUAL","="->comparison==0;case "<>"->comparison!=0;case ">"->comparison>0;case "<"->comparison<0;case ">="->comparison>=0;case "<="->comparison<=0;default->throw new IllegalArgumentException("edit-comparator");};}
        default:throw new IllegalArgumentException("edit-predicate");
    }}
    private void assign(JsonNode target,Value value,boolean string){
        if(target.path("op").asText().equals("field")){
            String name=target.path("name").asText();int n=field(name).path("length").asInt();String text=value.figurative()?figurative(value.text(),n):value.text();
            if(string){String previous=get(name);int length=Math.min(text.length(),previous.length());text=text.substring(0,length)+previous.substring(length);}
            put(name,text);return;
        }
        if(target.path("op").asText().equals("slice")&&target.path("operand").path("op").asText().equals("field")){
            String name=target.path("operand").path("name").asText(),old=get(name);int start=integer(target.path("start"))-1,n=integer(target.path("length"));
            if(start<0||n<1||start+n>old.length())throw new IllegalArgumentException("edit-reference-modification");
            String text=value.figurative()?figurative(value.text(),n):value.text();text=(text+" ".repeat(n)).substring(0,n);
            put(name,old.substring(0,start)+text+old.substring(start+n));return;
        }throw new IllegalArgumentException("edit-assignment-target");
    }
    private boolean execute(JsonNode statements){for(JsonNode statement:statements){visit(statement);switch(statement.path("op").asText()){
        case "if":if(execute(statement.path(test(statement.path("test"))?"yes":"no")))return true;break;
        case "set":setCondition(statement.path("name").asText());break;
        case "move":{Value value=evaluate(statement.path("value"));for(JsonNode target:statement.path("targets"))assign(target,value,false);break;}
        case "string":{StringBuilder text=new StringBuilder();for(JsonNode piece:statement.path("pieces"))text.append(evaluate(piece).text());assign(statement.path("target"),new Value(text.toString(),false,false),true);break;}
        case "convert":{JsonNode target=statement.path("target");String text=evaluate(target).text(),before=evaluate(statement.path("before")).text(),after=evaluate(statement.path("after")).text();
            if(before.length()!=after.length())throw new IllegalArgumentException("edit-conversion-length");StringBuilder converted=new StringBuilder();
            for(char c:text.toCharArray()){int index=before.indexOf(c);converted.append(index<0?c:after.charAt(index));}
            assign(target,new Value(converted.toString(),false,false),false);break;}
        case "return":return true;
        case "continue":break;
        default:throw new IllegalArgumentException("edit-statement");
    }}return false;}
    public void run(String paragraph){JsonNode statements=model.path("paragraphs").path(paragraph);
        if(statements.isMissingNode())throw new IllegalArgumentException("untranslated-edit-paragraph:"+paragraph);
        execute(statements);
    }
}
