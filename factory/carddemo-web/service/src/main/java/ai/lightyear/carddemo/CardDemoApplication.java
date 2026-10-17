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
    @Bean Bindings bindings(@Value("${carddemo.bindings}") String path,@Value("${carddemo.plan}") String plan)throws Exception{
        return new Bindings(Path.of(path),Path.of(plan),JsonMapper.builder().build());
    }
    @Bean SessionToken sessionToken(Bindings bindings,@Value("${carddemo.session-key}") String key){
        return new SessionToken(Base64.getDecoder().decode(key),bindings.hash,Clock.systemUTC(),JsonMapper.builder().build());
    }
    @Bean InteractionEngine engine(Bindings b,SessionToken tokens,DataSource database){
        return new InteractionEngine(b,tokens,database,Map.of("COSGN00C",new SignonService(b),"COMEN01C",new MenuService(b),"COACTVWC",new AccountViewService(b)));
    }
}
