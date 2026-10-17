package ai.lightyear.carddemo;

import java.math.*;
import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** Source-generated offsets, IBM big-endian binary, packed and zoned decimal. */
public final class Commarea {
    public static final Charset EBCDIC=Charset.forName("IBM037");
    private final JsonNode layout;private final byte[] bytes;
    public Commarea(JsonNode layout,byte[] previous){
        this.layout=layout;int length=layout.path("record_length").asInt();
        if(length<1||length>32767||(previous!=null&&previous.length!=length))throw new IllegalArgumentException("commarea-length");
        bytes=previous==null?new byte[length]:previous.clone();
        if(previous==null){Arrays.fill(bytes,(byte)0x40);BitSet initialized=new BitSet(length);
            // INITIALIZE excludes REDEFINES: first declaration owns each storage range.
            for(JsonNode f:layout.path("fields")){int off=f.path("offset").asInt(),len=f.path("length").asInt();
                if(initialized.get(off,off+len).isEmpty())write(f,f.path("digits").asInt()>0?"0":"");initialized.set(off,off+len);}
        }
    }
    private String leaf(JsonNode field){String path=field.path("path").asText();return path.substring(path.lastIndexOf('.')+1);}
    private JsonNode field(String name){JsonNode found=null;
        for(JsonNode f:layout.path("fields"))if(f.path("path").asText().equals(name)||leaf(f).equals(name)){
            if(found!=null)throw new IllegalArgumentException("ambiguous-commarea-field");found=f;}
        if(found==null)throw new IllegalArgumentException("unknown-commarea-field:"+name);return found;
    }
    public String get(String name){JsonNode f=field(name);int off=f.path("offset").asInt(),len=f.path("length").asInt(),digits=f.path("digits").asInt();
        byte[] raw=Arrays.copyOfRange(bytes,off,off+len);if(digits==0)return new String(raw,EBCDIC);
        BigInteger number;String usage=f.path("usage").asText();
        if(usage.equals("BINARY")||usage.equals("COMP-5"))number=f.path("signed").asBoolean()?new BigInteger(raw):new BigInteger(1,raw);
        else if(usage.equals("COMP-3")){
            StringBuilder decimal=new StringBuilder();for(int i=0;i<raw.length;i++){
                int high=(raw[i]>>>4)&15,low=raw[i]&15;if(high>9)throw new IllegalArgumentException("commarea-packed-digit");decimal.append(high);
                if(i<raw.length-1){if(low>9)throw new IllegalArgumentException("commarea-packed-digit");decimal.append(low);}
                else if(low!=12&&low!=13&&low!=15)throw new IllegalArgumentException("commarea-packed-sign");}
            number=new BigInteger(decimal.toString());if((raw[raw.length-1]&15)==13)number=number.negate();
        }else if(usage.equals("DISPLAY")){
            String text=new String(raw,EBCDIC);boolean negative=false;
            if(f.path("signed").asBoolean()){
                int at=f.path("sign").asText().equals("LEADING")?0:text.length()-1;
                if(f.path("separate").asBoolean()){
                    char sign=text.charAt(at);if(sign!='+'&&sign!='-')throw new IllegalArgumentException("commarea-display-sign");negative=sign=='-';text=text.substring(0,at)+text.substring(at+1);
                }else{char last=text.charAt(at);int pos="{ABCDEFGHI".indexOf(last),neg="}JKLMNOPQR".indexOf(last);
                    if(pos<0&&neg<0)throw new IllegalArgumentException("commarea-zoned-sign");negative=neg>=0;
                    text=text.substring(0,at)+(char)('0'+(negative?neg:pos))+text.substring(at+1);}
            }
            if(!text.matches("[0-9]+"))throw new IllegalArgumentException("commarea-display-digit");number=new BigInteger(text);if(negative)number=number.negate();
        }else throw new IllegalArgumentException("commarea-usage");
        String d=number.abs().toString();d="0".repeat(Math.max(0,digits-d.length()))+d;int scale=f.path("scale").asInt();
        if(scale>0)d=d.substring(0,d.length()-scale)+"."+d.substring(d.length()-scale);
        return number.signum()<0?"-"+d:d;
    }
    public void set(String name,String value){write(field(name),value);}
    private void write(JsonNode f,String value){int off=f.path("offset").asInt(),len=f.path("length").asInt(),digits=f.path("digits").asInt();byte[] raw;
        if(digits==0){if(value.length()>len)throw new IllegalArgumentException("commarea-text-length");raw=encode(value+" ".repeat(len-value.length()));}
        else{
            BigInteger number;try{number=new BigDecimal(value).setScale(f.path("scale").asInt(),RoundingMode.UNNECESSARY).unscaledValue();}
            catch(NumberFormatException|ArithmeticException invalid){throw new IllegalArgumentException("commarea-number",invalid);}
            String d=number.abs().toString();if(d.length()>digits||number.signum()<0&&!f.path("signed").asBoolean())throw new IllegalArgumentException("commarea-number-range");
            d="0".repeat(digits-d.length())+d;String usage=f.path("usage").asText();
            if(usage.equals("BINARY")||usage.equals("COMP-5")){
                int bits=len*8-(f.path("signed").asBoolean()?1:0);if(number.bitLength()>bits)throw new IllegalArgumentException("commarea-binary-range");
                byte[] n=number.toByteArray();raw=new byte[len];Arrays.fill(raw,number.signum()<0?(byte)0xff:(byte)0);
                int count=Math.min(n.length,len);System.arraycopy(n,n.length-count,raw,len-count,count);
            }else if(usage.equals("COMP-3")){
                String n="0".repeat(len*2-1-d.length())+d+(number.signum()<0?"D":f.path("signed").asBoolean()?"C":"F");raw=HexFormat.of().parseHex(n);
            }else if(usage.equals("DISPLAY")){
                if(f.path("signed").asBoolean()){
                    boolean leading=f.path("sign").asText().equals("LEADING");
                    if(f.path("separate").asBoolean())d=leading?(number.signum()<0?"-":"+")+d:d+(number.signum()<0?"-":"+");
                    else{int at=leading?0:d.length()-1;char sign=(number.signum()<0?"}JKLMNOPQR":"{ABCDEFGHI").charAt(d.charAt(at)-'0');d=d.substring(0,at)+sign+d.substring(at+1);}
                }raw=encode(d);
            }else throw new IllegalArgumentException("commarea-usage");
        }
        if(raw.length!=len)throw new IllegalArgumentException("commarea-encoding");System.arraycopy(raw,0,bytes,off,len);
    }
    public byte[] bytes(){return bytes.clone();}
    /** XCTL copies the actual common prefix; a different program's private tail is initialized. */
    public Commarea transition(JsonNode target,int commonLength,boolean preserveTail){
        Commarea next=new Commarea(target,null);int length=preserveTail?Math.min(bytes.length,next.bytes.length):commonLength;
        if(length>bytes.length||length>next.bytes.length)throw new IllegalArgumentException("commarea-transition-length");
        System.arraycopy(bytes,0,next.bytes,0,length);return next;
    }
    public static byte[] encode(String value){
        try{ByteBuffer out=EBCDIC.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value));
            byte[] raw=new byte[out.remaining()];out.get(raw);return raw;
        }catch(java.nio.charset.CharacterCodingException e){throw new IllegalArgumentException("not-cp037");}
    }
}
