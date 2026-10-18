package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.util.regex.Pattern;

/** Default dollar currency / decimal point grammar, IBM NUMVAL-C formats 1/2.
 * Source: IBM Enterprise COBOL 6.3 language reference, functions-numval-c.
 * This adapter is limited to the slice's display operands (at most 15 digits).
 * It exposes validity, not TEST-NUMVAL-C's unused invalid-character position.
 */
public final class CobolNumber {
    private CobolNumber() {}
    private static String spaces(String text){return text.replaceAll("^ +| +$","");}
    public static BigDecimal parse(String input,boolean currency){
        String value=spaces(input);boolean negative=false,signed=false;
        if(value.startsWith("+")||value.startsWith("-")){
            negative=value.charAt(0)=='-';signed=true;value=spaces(value.substring(1));
        }
        if(currency&&value.startsWith("$"))value=spaces(value.substring(1));
        String suffix=null;
        for(String candidate:new String[]{"CR","DB","+","-"})if(value.endsWith(candidate)){suffix=candidate;break;}
        if(suffix!=null){
            if(signed)throw new IllegalArgumentException("numval-two-signs");
            negative=!suffix.equals("+");value=spaces(value.substring(0,value.length()-suffix.length()));
        }
        String integer=currency?"[0-9]+(?:,[0-9]+)*":"[0-9]+";
        if(!Pattern.matches("(?:"+integer+"(?:[.][0-9]*)?|[.][0-9]+)",value))throw new IllegalArgumentException("numval-syntax");
        String decimal=value.replace(",","");
        if(decimal.replace(".","").length()>15)throw new IllegalArgumentException("numval-unproved-precision");
        BigDecimal result=new BigDecimal(decimal);
        return negative?result.negate():result;
    }
    public static boolean valid(String value,boolean currency){
        try{parse(value,currency);return true;}catch(IllegalArgumentException invalid){return false;}
    }
}
