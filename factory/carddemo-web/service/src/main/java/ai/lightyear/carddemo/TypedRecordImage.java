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
    /** Reconstruct unchanged bytes from typed columns and validated encoding metadata. */
    public static byte[] reconstruct(JsonNode mapping,Map<String,Object> row){
        JsonNode meta=JsonMapper.builder().build().readTree(row.get("encoding_meta").toString());
        if(meta.path("length").asInt()!=mapping.path("record_length").asInt()||!meta.path("codec").asText().equals("cp037"))throw new IllegalArgumentException("record-metadata-layout");
        Commarea buffer=new Commarea(mapping,null);BitSet covered=new BitSet(mapping.path("record_length").asInt());Set<String> seen=new HashSet<>();
        for(JsonNode active:meta.path("active")){
            JsonNode f=null;String path=active.path("path").asText();
            for(JsonNode candidate:mapping.path("fields"))if(candidate.path("path").asText().equals(path)){f=candidate;break;}
            if(f==null||!seen.add(path)||f.path("offset").asInt()!=active.path("offset").asInt()||f.path("length").asInt()!=active.path("length").asInt())throw new IllegalArgumentException("record-metadata-field");
            int off=f.path("offset").asInt(),len=f.path("length").asInt();
            if(!covered.get(off,off+len).isEmpty())throw new IllegalArgumentException("record-metadata-overlap");covered.set(off,off+len);
            if(f.path("filler").asBoolean())continue;
            String column=f.path("column").asText();Object value=row.get(column+(f.path("date").asBoolean()?"_raw":""));
            if(value==null)throw new IllegalArgumentException("record-missing-column");
            buffer.set(path,value instanceof byte[] raw?new String(raw,Commarea.EBCDIC):value.toString());
            JsonNode rep=meta.path("representations").path(path);
            // Python records null for unsigned DISPLAY and binary fields: no sign to restore.
            if(rep.hasNonNull("sign_code")){
                byte[] raw=buffer.bytes();boolean packed=f.path("usage").asText().equals("COMP-3");int index=packed?off+len-1:off+(f.path("sign").asText().equals("LEADING")?0:len-1);
                int sign=rep.path("sign_code").asInt();if(sign!=12&&sign!=13&&sign!=15)throw new IllegalArgumentException("record-sign-code");
                raw[index]=(byte)(packed?(raw[index]&240)|sign:(raw[index]&15)|(sign<<4));buffer.copyBytes(index,new byte[]{raw[index]});
            }
        }
        for(JsonNode filler:meta.path("filler")){int off=filler.path("offset").asInt();byte[] bytes=HexFormat.of().parseHex(filler.path("hex").asText());boolean declared=false;
            for(JsonNode f:mapping.path("fields"))if(f.path("filler").asBoolean()&&f.path("offset").asInt()==off&&f.path("length").asInt()==bytes.length)declared=true;
            if(!declared)throw new IllegalArgumentException("record-filler-layout");buffer.copyBytes(off,bytes);}
        if(covered.cardinality()!=mapping.path("record_length").asInt())throw new IllegalArgumentException("record-unaccounted-storage");
        byte[] raw=buffer.bytes();try{if(!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw)).equals(row.get("source_sha256").toString().strip()))throw new IllegalArgumentException("record-hash-mismatch");}
        catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}return raw;
    }
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
