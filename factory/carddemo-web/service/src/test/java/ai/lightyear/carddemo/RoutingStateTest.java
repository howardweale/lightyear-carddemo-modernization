package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.Connection;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

/** Direct transaction boundaries retain observations that a following XCTL can overwrite. */
class RoutingStateTest {
    Bindings bindings()throws Exception{Path root=Path.of(System.getProperty("carddemo.root"));return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());}
    @Test void accountPf3UsesCallerOrSourceDefaultsAndResetsUserContext()throws Exception{
        var b=bindings();Connection db=mock(Connection.class);
        for(String program:List.of("COACTVWC","COACTUPC"))for(String caller:List.of("CALLER01","", "\u0000".repeat(8))){
            var area=new Commarea(b.root.path("program_commareas").path(program),null);
            area.set("CDEMO-FROM-PROGRAM",caller);area.set("CDEMO-FROM-TRANID",caller.equals("CALLER01")?"CA01":caller.isEmpty()?"":"\u0000".repeat(4));
            area.set("CDEMO-USER-TYPE","A");area.set("CDEMO-PGM-CONTEXT","1");
            TransactionService service=program.equals("COACTVWC")?new AccountViewService(b):new AccountUpdateService(b);
            var result=service.interact(db,area,"PF3",Map.of());var constants=b.program(program).path("constants");
            assertEquals(caller.equals("CALLER01")?caller:constants.path("LIT-MENUPGM").asText(),result.nextProgram());
            assertEquals(result.nextProgram(),area.get("CDEMO-TO-PROGRAM").stripTrailing());
            assertEquals(caller.equals("CALLER01")?"CA01":constants.path("LIT-MENUTRANID").asText(),area.get("CDEMO-TO-TRANID").stripTrailing());
            assertEquals(program,area.get("CDEMO-FROM-PROGRAM"));assertEquals(b.screen(program).path("transaction").asText(),area.get("CDEMO-FROM-TRANID"));
            assertEquals("U",area.get("CDEMO-USER-TYPE"));assertEquals("0",area.get("CDEMO-PGM-CONTEXT"));
            assertEquals(constants.path("LIT-THISMAPSET").asText().stripTrailing(),area.get("CDEMO-LAST-MAPSET").stripTrailing());
            assertEquals(constants.path("LIT-THISMAP").asText().stripTrailing(),area.get("CDEMO-LAST-MAP").stripTrailing());
        }verifyNoInteractions(db);
    }
    @Test void authorizationReturnAndInvalidAidExposeStateBeforeTheNextProgram()throws Exception{
        var b=bindings();Connection db=mock(Connection.class);
        for(String program:List.of("COPAUS0C","COPAUS1C")){
            var area=new Commarea(b.root.path("program_commareas").path(program),null);area.set("CDEMO-PGM-CONTEXT","1");
            if(program.equals("COPAUS1C"))area.set("CDEMO-CPVD-FRAUD-DATA","STALE");
            TransactionService service=program.equals("COPAUS0C")?new AuthorizationListService(b):new AuthorizationDetailService(b);
            var result=service.interact(db,area,"PF3",Map.of());
            assertEquals(program.equals("COPAUS0C")?"COMEN01C":"COPAUS0C",result.nextProgram());
            assertEquals(result.nextProgram(),area.get("CDEMO-TO-PROGRAM"));assertEquals(program,area.get("CDEMO-FROM-PROGRAM"));
            assertEquals(result.screen().transaction,area.get("CDEMO-FROM-TRANID"));assertEquals("0",area.get("CDEMO-PGM-CONTEXT"));
            if(program.equals("COPAUS1C"))assertTrue(area.get("CDEMO-CPVD-FRAUD-DATA").isBlank());
            var invalid=service.interact(db,area,"PF24",Map.of());
            // Preserve the fixed-width source literal, including its trailing spaces.
            String invalidKey=b.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText();
            assertEquals(invalidKey,invalid.screen().message);
            assertEquals(ScreenFrame.pad(invalidKey,invalid.screen().values.get("ERRMSG").length()),invalid.screen().values.get("ERRMSG"));
        }verifyNoInteractions(db);
    }
    @Test void invalidAccountClearsStaleSearchAndPaginationAndFifthSelectionIsReachable()throws Exception{
        var b=bindings();Connection db=mock(Connection.class);
        for(String account:List.of("","ABCDEFGHIJK")){
            var view=new Commarea(b.root.path("program_commareas").path("COACTVWC"),null);view.set("CDEMO-ACCT-ID","12345678901");
            new AccountViewService(b).interact(db,view,"ENTER",Map.of("ACCTSID",account));assertEquals("00000000000",view.get("CDEMO-ACCT-ID"));
            var list=new Commarea(b.root.path("program_commareas").path("COPAUS0C"),null);list.set("CDEMO-CPVS-PAGE-NUM","9");
            var result=new AuthorizationListService(b).interact(db,list,"ENTER",Map.of("ACCTID",account));
            assertEquals(0,Integer.parseInt(list.get("CDEMO-CPVS-PAGE-NUM")));assertTrue(result.screen().values.get("ACCTID").isBlank());
        }
        var list=new Commarea(b.root.path("program_commareas").path("COPAUS0C"),null);list.set("CDEMO-CPVS-AUTH-KEYS[5]","FIFTHKEY");
        var result=new AuthorizationListService(b).interact(db,list,"ENTER",Map.of("ACCTID","00000000050","SEL0005","S"));
        assertEquals("COPAUS1C",result.nextProgram());assertEquals("FIFTHKEY",list.get("CDEMO-CPVS-PAU-SELECTED"));verifyNoInteractions(db);
    }
}
