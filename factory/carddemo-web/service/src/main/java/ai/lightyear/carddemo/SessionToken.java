package ai.lightyear.carddemo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import tools.jackson.databind.json.JsonMapper;

/** Stateless COMMAREA envelope. This key cannot sign Factory requests. */
public final class SessionToken {
    private static final byte[] DOMAIN="CardDemo COMMAREA session v2\0".getBytes(StandardCharsets.US_ASCII);
    private static final int MAX_TOKEN=100000;
    private final byte[] key;
    private final String sourceHash;
    private final Clock clock;
    private final JsonMapper json;
    public record Terminal(java.util.Map<String,String> values,java.util.Map<String,java.util.Map<String,Object>> attributes,String cursor,String message,String endpoint) {}
    public record State(int version,String sourceHash,String program,String commarea,Terminal terminal,long issued,long expires) {}

    public SessionToken(byte[] key,String sourceHash,Clock clock,JsonMapper json) {
        if(key.length<32 || !sourceHash.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("session-configuration");
        this.key=key.clone();this.sourceHash=sourceHash;this.clock=clock;this.json=json;
    }
    public String issue(String program,byte[] commarea) {
        return issue(program,commarea,null);
    }
    public String issue(String program,byte[] commarea,ScreenFrame frame) {
        if(frame!=null&&!frame.program.equals(program))throw new IllegalArgumentException("session-screen-program");
        Terminal terminal=frame==null?null:new Terminal(frame.values,frame.attributes,frame.cursor,frame.message,frame.endpoint);
        if(!program.matches("[A-Z0-9]{8}") || commarea.length>32767)throw new IllegalArgumentException("session-shape");
        long now=clock.instant().getEpochSecond();
        byte[] data=json.writeValueAsBytes(new State(2,sourceHash,program,Base64.getEncoder().encodeToString(commarea),terminal,now,now+1800));
        String encoded=Base64.getUrlEncoder().withoutPadding().encodeToString(data);
        String token=encoded+"."+Base64.getUrlEncoder().withoutPadding().encodeToString(mac(encoded));
        if(token.length()>MAX_TOKEN)throw new IllegalArgumentException("session-too-large");
        return token;
    }
    public State verify(String token) {
        try {
            if(token==null || token.length()>MAX_TOKEN)throw new IllegalArgumentException();
            String[] parts=token.split("\\.",-1);
            if(parts.length!=2 || !parts[0].matches("[A-Za-z0-9_-]+") || !parts[1].matches("[A-Za-z0-9_-]{43}"))throw new IllegalArgumentException();
            byte[] signature=Base64.getUrlDecoder().decode(parts[1]);
            if(!MessageDigest.isEqual(mac(parts[0]),signature))throw new IllegalArgumentException();
            State state=json.readValue(Base64.getUrlDecoder().decode(parts[0]),State.class);
            long now=clock.instant().getEpochSecond();
            if(state.version()!=2 || !sourceHash.equals(state.sourceHash()) || !state.program().matches("[A-Z0-9]{8}")
                || state.issued()>now || state.expires()!=state.issued()+1800 || now>=state.expires()
                || Base64.getDecoder().decode(state.commarea()).length>32767)throw new IllegalArgumentException();
            return state;
        } catch(RuntimeException invalid) {throw new IllegalArgumentException("session-invalid");}
    }
    private byte[] mac(String encoded) {
        try {Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(key,"HmacSHA256"));
            mac.update(DOMAIN);return mac.doFinal(encoded.getBytes(StandardCharsets.US_ASCII));
        }catch(java.security.GeneralSecurityException e){throw new IllegalStateException(e);}
    }
}
