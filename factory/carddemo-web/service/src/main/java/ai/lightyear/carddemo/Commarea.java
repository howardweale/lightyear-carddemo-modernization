package ai.lightyear.carddemo;

import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.util.Arrays;
import tools.jackson.databind.JsonNode;

/** Offsets, lengths and field types come only from the copybook compiler. */
public final class Commarea {
    public static final Charset EBCDIC=Charset.forName("IBM037");
    private final JsonNode layout;
    private final byte[] bytes;
    public Commarea(JsonNode layout,byte[] previous) {
        this.layout=layout;
        int length=layout.path("record_length").asInt();
        if(length<1 || length>32767 || (previous!=null && previous.length!=length))throw new IllegalArgumentException("commarea-length");
        bytes=previous==null?new byte[length]:previous.clone();
        if(previous==null)for(JsonNode f:layout.path("fields"))set(leaf(f),f.path("digits").asInt()>0?"0":"");
    }
    private String leaf(JsonNode field){String path=field.path("path").asText();return path.substring(path.lastIndexOf('.')+1);}
    private JsonNode field(String name){
        JsonNode found=null;
        for(JsonNode f:layout.path("fields"))if(leaf(f).equals(name)){if(found!=null)throw new IllegalArgumentException("ambiguous-commarea-field");found=f;}
        if(found==null)throw new IllegalArgumentException("unknown-commarea-field:"+name);
        if(!found.path("usage").asText().equals("DISPLAY"))throw new IllegalArgumentException("commarea-usage");
        return found;
    }
    public String get(String name){JsonNode f=field(name);int offset=f.path("offset").asInt();
        return new String(bytes,offset,f.path("length").asInt(),EBCDIC);}
    public void set(String name,String value){
        JsonNode f=field(name);int offset=f.path("offset").asInt(),length=f.path("length").asInt();
        boolean numeric=f.path("digits").asInt()>0;
        if(value.length()>length || (numeric && !value.matches("[0-9]+")))throw new IllegalArgumentException("commarea-value:"+name);
        String padded=numeric?"0".repeat(length-value.length())+value:value+" ".repeat(length-value.length());
        byte[] raw=encode(padded);if(raw.length!=length)throw new IllegalArgumentException("commarea-encoding");
        System.arraycopy(raw,0,bytes,offset,length);
    }
    public byte[] bytes(){return bytes.clone();}
    public static byte[] encode(String value){
        try {ByteBuffer out=EBCDIC.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value));
            byte[] raw=new byte[out.remaining()];out.get(raw);return raw;
        }catch(java.nio.charset.CharacterCodingException e){throw new IllegalArgumentException("not-cp037");}
    }
}
