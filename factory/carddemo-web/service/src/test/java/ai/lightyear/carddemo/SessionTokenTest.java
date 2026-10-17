package ai.lightyear.carddemo;

import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

class SessionTokenTest {
    private final byte[] key=new byte[32]; // Disposable CI-only fixture, never a Factory authority key.
    private final JsonMapper json=JsonMapper.builder().build();
    private SessionToken codec(long seconds,String hash){return new SessionToken(key,hash,Clock.fixed(Instant.ofEpochSecond(seconds),ZoneOffset.UTC),json);}
    @Test void bytesAndProgramAreBound(){
        SessionToken codec=codec(100,"a".repeat(64));byte[] raw={0,1,(byte)255,64};
        String token=codec.issue("COSGN00C",raw);SessionToken.State state=codec.verify(token);
        assertArrayEquals(raw,Base64.getDecoder().decode(state.commarea()));assertEquals("COSGN00C",state.program());
        char changed=token.charAt(5)=='a'?'b':'a';String tampered=token.substring(0,5)+changed+token.substring(6);
        assertThrows(IllegalArgumentException.class,()->codec.verify(tampered));
        assertThrows(IllegalArgumentException.class,()->codec(100,"b".repeat(64)).verify(token));
        assertThrows(IllegalArgumentException.class,()->new SessionToken(new byte[31],"a".repeat(64),Clock.systemUTC(),json));
    }
    @Test void expiry_is_exclusive_and_future_tokens_refused(){
        String token=codec(100,"a".repeat(64)).issue("COMEN01C",new byte[5]);
        assertNotNull(codec(1899,"a".repeat(64)).verify(token));
        assertThrows(IllegalArgumentException.class,()->codec(1900,"a".repeat(64)).verify(token));
        assertThrows(IllegalArgumentException.class,()->codec(99,"a".repeat(64)).verify(token));
    }
}
