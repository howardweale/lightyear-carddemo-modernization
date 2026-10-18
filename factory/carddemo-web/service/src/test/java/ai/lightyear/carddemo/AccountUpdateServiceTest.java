package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.Connection;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

class AccountUpdateServiceTest {
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());
    }
    @Test void initialEmptyAndInvalidSearchUseSourceMessagesWithoutDatabaseAccess()throws Exception{
        var b=bindings();var service=new AccountUpdateService(b);Connection db=mock(Connection.class);
        var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        var first=service.interact(db,area,"INITIAL",Map.of());
        assertEquals(false,first.screen().attributes.get("ACCTSID").get("protected"));
        assertEquals(true,first.screen().attributes.get("ACSFNAM").get("protected"));
        var blank=service.interact(db,area,"ENTER",Map.of("ACCTSID",""),first.screen());
        assertEquals("No input received",blank.screen().message);assertEquals("ACCTSID",blank.screen().cursor);
        var invalid=service.interact(db,area,"ENTER",Map.of("ACCTSID","ABCDEFGHIJK"),blank.screen());
        assertEquals("Account Number if supplied must be a 11 digit Non-Zero Number",invalid.screen().message);
        assertEquals("RED",invalid.screen().attributes.get("ACCTSID").get("color"));verifyNoInteractions(db);
    }
    @Test void missingCrossReferenceRetainsSearchKeyAndClearsOldDetailsBeforeEachRead()throws Exception{
        var b=bindings();var service=new AccountUpdateService(b);Connection db=mock(Connection.class);
        var query=mock(java.sql.PreparedStatement.class);var rows=mock(java.sql.ResultSet.class);
        when(db.prepareStatement(anyString())).thenReturn(query);when(query.executeQuery()).thenReturn(rows);when(rows.next()).thenReturn(false);
        var layout=b.root.path("program_commareas").path("COACTUPC");var area=new Commarea(layout,null);
        var prior=service.interact(db,area,"INITIAL",Map.of()).screen();
        for(String account:java.util.List.of("99999999999","88888888888")){
            area.set("ACUP-OLD-ACCT-ID","12345678901");area.set("ACUP-OLD-GROUP-ID","STALE");
            var result=service.interact(db,area,"ENTER",Map.of("ACCTSID",account),prior);
            assertTrue(result.screen().message.contains("not found in Cross ref file"));
            assertEquals(account,area.get("ACUP-OLD-ACCT-ID"));
            assertEquals(" ".repeat(area.get("ACUP-OLD-GROUP-ID").length()),area.get("ACUP-OLD-GROUP-ID"));
            verify(query).setBytes(1,Commarea.encode(account));prior=result.screen();
        }
        verify(db,times(2)).prepareStatement(startsWith("SELECT * FROM \"cardxref\""));
        verify(db,never()).commit();verify(query,never()).executeUpdate();
    }
    @Test void pf3ReturnsToCallerWithoutReceivingInvalidInput()throws Exception{
        var b=bindings();var service=new AccountUpdateService(b);Connection db=mock(Connection.class);
        var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        area.set("CDEMO-FROM-PROGRAM","COMEN01C");area.set("CDEMO-FROM-TRANID","CM00");
        var result=service.interact(db,area,"PF3",Map.of("not-a-field","ignored"));
        assertEquals("COMEN01C",result.nextProgram());assertEquals("COACTUPC",area.get("CDEMO-FROM-PROGRAM"));verifyNoInteractions(db);
    }
    @Test void signedTerminalStatePreservesProtectedMdtValuesAndRejectsTampering()throws Exception{
        var b=bindings();var frame=new ScreenFrame(b,"COACTUPC");frame.set("ACSCTRY","USA");
        var codec=new SessionToken(new byte[32],b.hash,java.time.Clock.systemUTC(),JsonMapper.builder().build());
        var area=new Commarea(b.root.path("program_commareas").path("COACTUPC"),null);
        String token=codec.issue("COACTUPC",area.bytes(),frame);var state=codec.verify(token);
        var restored=new ScreenFrame(b,"COACTUPC");restored.restore(state.terminal());
        assertEquals(frame.values,restored.values);assertEquals(frame.attributes.get("ACSCTRY").get("protected"),restored.attributes.get("ACSCTRY").get("protected"));
        int at=token.indexOf('.');char replacement=token.charAt(at-1)=='A'?'B':'A';
        assertThrows(IllegalArgumentException.class,()->codec.verify(token.substring(0,at-1)+replacement+token.substring(at)));
    }
}
