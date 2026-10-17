package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.security.*;
import java.time.LocalDate;
import java.util.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Re-project a COBOL rewrite buffer by byte offsets into the migrated schema.
 * In particular, differently named layouts are never joined by field names.
 */
public final class TypedRecordImage {
    private TypedRecordImage(){}
    public record Image(Map<String,Object> columns,String metadata,String sha256){}
    public static Image project(JsonNode mapping,byte[] raw){
        if(raw.length!=mapping.path("record_length").asInt())throw new IllegalArgumentException("rewrite-record-length");
        Commarea decoded=new Commarea(mapping,raw);Map<String,Object> values=new LinkedHashMap<>(),representations=new LinkedHashMap<>();
        List<Object> active=new ArrayList<>(),filler=new ArrayList<>();BitSet covered=new BitSet(raw.length);
        for(JsonNode f:mapping.path("fields")){
            String path=f.path("path").asText();int off=f.path("offset").asInt(),len=f.path("length").asInt();
            if(off<0||len<1||off+len>raw.length||!covered.get(off,off+len).isEmpty())throw new IllegalArgumentException("rewrite-layout-overlap");
            if(!f.path("table").asText().equals(mapping.path("table").asText())||!f.path("ordinal").isNull())throw new IllegalArgumentException("rewrite-child-layout");
            covered.set(off,off+len);byte[] bytes=Arrays.copyOfRange(raw,off,off+len);
            active.add(Map.of("path",path,"offset",off,"length",len));
            if(f.path("filler").asBoolean()){filler.add(Map.of("offset",off,"hex",HexFormat.of().formatHex(bytes)));continue;}
            String column=f.path("column").asText();Map<String,Object> representation=new LinkedHashMap<>();
            if(f.path("digits").asInt()>0){
                BigDecimal number=new BigDecimal(decoded.get(path));values.put(column,number);
                String usage=f.path("usage").asText();
                if(usage.equals("COMP-3")||(usage.equals("DISPLAY")&&f.path("signed").asBoolean()&&!f.path("separate").asBoolean())){
                    int sign=usage.equals("COMP-3")?bytes[len-1]&15:(bytes[f.path("sign").asText().equals("LEADING")?0:len-1]>>>4)&15;
                    representation.put("sign_code",sign);representation.put("negative_zero",number.signum()==0&&sign==13);
                }
            }else if(f.path("date").asBoolean()){
                String text=new String(bytes,Commarea.EBCDIC);
                if(!text.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}"))throw new IllegalArgumentException("rewrite-date-format");
                values.put(column,java.sql.Date.valueOf(LocalDate.parse(text)));values.put(column+"_raw",text);
            }else values.put(column,bytes);
            representations.put(path,representation);
        }
        if(covered.cardinality()!=raw.length)throw new IllegalArgumentException("rewrite-unaccounted-storage");
        for(JsonNode key:mapping.path("keys")){
            int start=key.path("key_offset").asInt(),length=key.path("key_length").asInt();
            if(start<0||length<1||start+length>raw.length)throw new IllegalArgumentException("rewrite-key-layout");
            values.put(key.path("column").asText(),Arrays.copyOfRange(raw,start,start+length));
        }
        var metadata=Map.of("length",raw.length,"active",active,"filler",filler,"representations",representations,"codec","cp037");
        try{return new Image(values,JsonMapper.builder().build().writeValueAsString(metadata),HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw)));}
        catch(NoSuchAlgorithmException error){throw new IllegalStateException(error);}
    }
}
