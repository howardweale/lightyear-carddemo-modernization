package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.time.Clock;
import java.util.*;
import javax.sql.DataSource;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import tools.jackson.databind.json.JsonMapper;

@SpringBootApplication
public class CardDemoApplication {
    public static void main(String[] args){SpringApplication.run(CardDemoApplication.class,args);}
    @Bean Bindings bindings(@Value("${carddemo.bindings}") String path,@Value("${carddemo.plan}") String plan,
                           @Value("${carddemo.reference-instant:}") String instant,org.springframework.core.env.Environment environment)throws Exception{
        Clock clock=Clock.systemUTC();
        if(!instant.isEmpty()){
            if(!environment.acceptsProfiles(org.springframework.core.env.Profiles.of("reference-ci")))throw new IllegalArgumentException("fixed-clock-requires-reference-ci-profile");
            clock=Clock.fixed(java.time.Instant.parse(instant),java.time.ZoneOffset.UTC);
        }
        // Session expiration still uses the real clock; only screen/business date ports are fixed in CI.
        return new Bindings(Path.of(path),Path.of(plan),JsonMapper.builder().build(),clock);
    }
    @Bean SessionToken sessionToken(Bindings bindings,@Value("${carddemo.session-key}") String key){
        byte[] sessionKey;
        if(key.isEmpty()){sessionKey=new byte[32];new java.security.SecureRandom().nextBytes(sessionKey);}
        else sessionKey=Base64.getDecoder().decode(key);
        return new SessionToken(sessionKey,bindings.hash,Clock.systemUTC(),JsonMapper.builder().build());
    }
    @Bean InteractionEngine engine(Bindings b,SessionToken tokens,DataSource database){
        return new InteractionEngine(b,tokens,database,Map.of("COSGN00C",new SignonService(b),"COMEN01C",new MenuService(b),"COACTVWC",new AccountViewService(b),"COACTUPC",new AccountUpdateService(b),"COPAUS0C",new AuthorizationListService(b),"COPAUS1C",new AuthorizationDetailService(b)));
    }
}
