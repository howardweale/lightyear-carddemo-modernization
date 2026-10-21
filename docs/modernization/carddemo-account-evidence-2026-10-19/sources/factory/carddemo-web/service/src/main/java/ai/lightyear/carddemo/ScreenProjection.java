package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** Execute generated MOVE/STRING expressions; business conditions live in the handler. */
public final class ScreenProjection {
    private final Bindings bindings;private final TypedRecords records;
    public ScreenProjection(Bindings bindings){this.bindings=bindings;records=new TypedRecords(bindings);}
    private String table(String field){String result=null;
        for(JsonNode mapping:bindings.data.path("mappings"))for(JsonNode f:mapping.path("fields")){
            String path=f.path("path").asText();if(!path.substring(path.lastIndexOf('.')+1).equals(field))continue;
            if(result!=null)throw new IllegalArgumentException("projection-field-ambiguous");result=mapping.path("table").asText();}
        if(result==null)throw new IllegalArgumentException("projection-field-unmapped:"+field);return result;}
    private String value(String name,Map<String,Map<String,Object>> rows){String t=table(name);
        Map<String,Object> row=rows.get(t);return row==null?null:records.text(t,row,name);}
    public void apply(ScreenFrame frame,JsonNode expressions,Map<String,Map<String,Object>> rows){
        for(JsonNode e:expressions){String value;
            if(e.path("operation").asText().equals("move"))value=value(e.path("field").asText(),rows);
            else if(e.path("operation").asText().equals("string")){
                StringBuilder b=new StringBuilder();boolean absent=false;
                for(JsonNode piece:e.path("pieces")){
                    if(piece.has("literal")){b.append(piece.path("literal").asText());continue;}
                    String v=value(piece.path("field").asText(),rows);if(v==null){absent=true;break;}
                    int offset=piece.path("offset").asInt(),length=piece.path("length").asInt();
                    if(offset<0 || length<1 || offset+length>v.length())throw new IllegalArgumentException("projection-reference-modification");
                    b.append(v,offset,offset+length);
                }value=absent?null:b.toString();
            }else throw new IllegalArgumentException("projection-operation");
            if(value!=null){String target=e.path("target").asText();JsonNode picture=frame.field(target).path("output_picture");
                if(!picture.isMissingNode() && !picture.isNull())value=edited(value,picture.asText());
                frame.set(target,value);}
        }
    }
    /** Bounded numeric-editing grammar present in these BMS maps; unknown pictures refuse. */
    public static String edited(String value,String quotedPicture){
        String picture=quotedPicture.replace("'","").toUpperCase(Locale.ROOT);
        if(!picture.matches("[+-][Z9]+(,[Z9]+)*\\.9+"))throw new IllegalArgumentException("unsupported-edited-picture");
        BigDecimal n=new BigDecimal(value);int point=picture.indexOf('.'),scale=picture.length()-point-1;
        String fixed=n.abs().setScale(scale,RoundingMode.DOWN).toPlainString();String[] parts=fixed.split("\\.",-1);
        int digits=(int)picture.substring(1,point).chars().filter(c->c=='Z'||c=='9').count();
        // COBOL numeric editing truncates high-order digits on receiving-field overflow.
        String integer=parts[0];if(integer.length()>digits)integer=integer.substring(integer.length()-digits);
        integer="0".repeat(Math.max(0,digits-integer.length()))+integer;
        char[] out=picture.toCharArray();int pos=0;boolean significant=false;
        out[0]=n.signum()<0?'-':picture.charAt(0)=='+'?'+':' ';
        for(int i=1;i<point;i++){
            if(out[i]=='Z'||out[i]=='9'){char d=integer.charAt(pos++);if(d!='0'||out[i]=='9')significant=true;out[i]=significant?d:' ';}
            else if(!significant)out[i]=' ';
        }
        for(int i=point+1;i<out.length;i++)out[i]=parts.length>1?parts[1].charAt(i-point-1):'0';
        return new String(out);
    }
}
