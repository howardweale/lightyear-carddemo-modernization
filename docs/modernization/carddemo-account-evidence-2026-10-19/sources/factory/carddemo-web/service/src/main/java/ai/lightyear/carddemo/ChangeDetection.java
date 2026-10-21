package ai.lightyear.carddemo;

import java.util.Locale;
import java.util.function.Function;
import tools.jackson.databind.JsonNode;

/** Exact generated comparison expression trees, including source reference modifications. */
public final class ChangeDetection {
    private ChangeDetection(){}
    public static String evaluate(JsonNode e,Function<String,String> fields){
        String operation=e.path("operation").asText();
        if(operation.equals("field")){
            String value=fields.apply(e.path("name").asText());if(value==null)throw new IllegalArgumentException("comparison-field-absent");
            if(e.has("offset")){int start=e.path("offset").asInt(),length=e.path("length").asInt();
                if(start<0||length<1||start+length>value.length())throw new IllegalArgumentException("comparison-reference-modification");value=value.substring(start,start+length);}
            return value;
        }
        String value=evaluate(e.path("operand"),fields);
        return switch(operation){
            case "UPPER-CASE" -> value.toUpperCase(Locale.ROOT);
            case "LOWER-CASE" -> value.toLowerCase(Locale.ROOT);
            case "TRIM" -> value.replaceAll("^ +| +$","");
            default -> throw new IllegalArgumentException("comparison-operation");
        };
    }
    public static boolean equal(JsonNode comparisons,Function<String,String> fields){
        if(!comparisons.isArray()||comparisons.isEmpty())throw new IllegalArgumentException("comparison-inventory");
        for(JsonNode pair:comparisons){String left=evaluate(pair.path("left"),fields),right=evaluate(pair.path("right"),fields);
            int length=Math.max(left.length(),right.length());
            if(!ScreenFrame.pad(left,length).equals(ScreenFrame.pad(right,length)))return false;
        }return true;
    }
}
