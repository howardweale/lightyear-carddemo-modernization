package ai.lightyear.carddemo;

import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

class GeneratedBindingsTest {
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());
    }
    @Test void generatedCommareaRoundTripsWithoutSharedMutableState()throws Exception{
        Bindings b=bindings();Commarea a=new Commarea(b.root.path("commarea"),null);
        a.set("CDEMO-USER-ID","USER0001");a.set("CDEMO-ACCT-ID","123");
        assertEquals("00000000123",a.get("CDEMO-ACCT-ID"));
        byte[] exported=a.bytes();exported[0]=1;
        assertFalse(Arrays.equals(exported,a.bytes()));
        Commarea restored=new Commarea(b.root.path("commarea"),a.bytes());
        assertEquals("USER0001",restored.get("CDEMO-USER-ID"));
        restored.set("CDEMO-USER-ID","OTHER");assertEquals("USER0001",a.get("CDEMO-USER-ID"));
        assertThrows(IllegalArgumentException.class,()->a.set("CDEMO-ACCT-ID","abc"));
        assertThrows(IllegalArgumentException.class,()->a.set("CDEMO-USER-ID","too-long-value"));
        assertThrows(IllegalArgumentException.class,()->Commarea.encode("\uD83D\uDE42"));
    }
    @Test void menuJustificationAndEveryOutsideOptionAreSourceDerived()throws Exception{
        Bindings b=bindings();MenuService menu=new MenuService(b);
        for(int i=1;i<=11;i++){
            Commarea area=new Commarea(b.root.path("commarea"),null);area.set("CDEMO-USER-TYPE","U");
            var result=menu.interact(null,area,"ENTER",Map.of("OPTION",Integer.toString(i)));
            var source=b.root.path("menu").get(i-1);
            assertEquals(source.path("program").asText(),result.nextProgram());
            assertEquals(source.path("in_slice").asBoolean()?"":"/not-in-this-slice",result.screen().endpoint);
            assertEquals("COMEN01C",area.get("CDEMO-FROM-PROGRAM"));
        }
        for(String invalid:List.of("","00","12","AA")){
            var result=menu.interact(null,new Commarea(b.root.path("commarea"),null),"ENTER",Map.of("OPTION",invalid));
            assertEquals("COMEN01C",result.nextProgram());assertEquals("Please enter a valid option number...",result.screen().message);
        }
    }
    @Test void protectionAndSourceMessageChangesFailClosed()throws Exception{
        Bindings b=bindings();ScreenFrame screen=new ScreenFrame(b,"COSGN00C");
        assertThrows(IllegalArgumentException.class,()->screen.receive(Map.of("TITLE01","overwrite")));
        assertThrows(IllegalArgumentException.class,()->screen.receive(Map.of("invented","value")));
        assertThrows(IllegalArgumentException.class,()->screen.receive(Map.of("USERID","123456789")));
        assertThrows(IllegalArgumentException.class,()->b.literal("COSGN00C","invented placeholder"));
        assertEquals("ABC     ",screen.receive(Map.of("USERID","ABC")).get("USERID"));
    }
}
