package ai.lightyear.carddemo;

import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class NumericEncodingTest {
    private JsonNode layout(String usage,int digits,int length,boolean signed)throws Exception{
        return JsonMapper.builder().build().readTree("{\"record_length\":"+length+",\"fields\":[{\"path\":\"R.N\",\"offset\":0,\"length\":"+length
            +",\"digits\":"+digits+",\"scale\":0,\"usage\":\""+usage+"\",\"signed\":"+signed+",\"sign\":\"TRAILING\",\"separate\":false}]}");
    }
    @Test void preferredZonedSignsAndInvalidZonesAreDistinguished()throws Exception{
        var layout=layout("DISPLAY",3,3,true);
        for(String raw:new String[]{"f1f2c3","f1f2f3"})assertEquals("123",new Commarea(layout,HexFormat.of().parseHex(raw)).get("N"));
        assertEquals("-123",new Commarea(layout,HexFormat.of().parseHex("f1f2d3")).get("N"));
        for(String raw:new String[]{"f1f2a3","f1f2b3","f1f2e3","c1f2c3","f1f2ca"})
            assertThrows(IllegalArgumentException.class,()->new Commarea(layout,HexFormat.of().parseHex(raw)).get("N"));
    }
    @Test void packedPaddingAndUnsignedSignsAreNotSilentlyAccepted()throws Exception{
        var even=layout("COMP-3",2,2,true);
        assertEquals("12",new Commarea(even,HexFormat.of().parseHex("012c")).get("N"));
        assertThrows(IllegalArgumentException.class,()->new Commarea(even,HexFormat.of().parseHex("112c")).get("N"));
        var unsigned=layout("COMP-3",3,2,false);
        assertEquals("123",new Commarea(unsigned,HexFormat.of().parseHex("123f")).get("N"));
        for(String raw:new String[]{"123c","123d"})assertThrows(IllegalArgumentException.class,()->new Commarea(unsigned,HexFormat.of().parseHex(raw)).get("N"));
    }
    @Test void binaryValueCannotExceedItsDeclaredPicture()throws Exception{
        var binary=layout("BINARY",3,2,true);
        assertEquals("999",new Commarea(binary,HexFormat.of().parseHex("03e7")).get("N"));
        assertThrows(IllegalArgumentException.class,()->new Commarea(binary,HexFormat.of().parseHex("03e8")).get("N"));
        var nativeBinary=new Commarea(layout("COMP-5",3,2,true),null);nativeBinary.set("N","32767");
        assertEquals("32767",nativeBinary.get("N"));assertArrayEquals(HexFormat.of().parseHex("7fff"),nativeBinary.bytes());
        assertThrows(IllegalArgumentException.class,()->nativeBinary.set("N","32768"));
    }
}
