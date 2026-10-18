package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.*;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

/** COSGN00C WORKING-STORAGE and lines 121-149: SEND does not end the paragraph. */
class SignonCommareaTest {
    private Bindings bindings()throws Exception{
        Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());
    }
    @Test void rejectedCredentialsReturnSubmittedIdAndClearPreviousInvocationState()throws Exception{
        var b=bindings();var service=new SignonService(b);var layout=b.root.path("program_commareas").path("COSGN00C");
        for(String user:new String[]{"", "alice"}){
            var area=new Commarea(layout,null);area.set("CDEMO-USER-ID","OLDUSER");area.set("CDEMO-FROM-PROGRAM","COMEN01C");area.set("CDEMO-ACCT-ID","50");
            Connection db=mock(Connection.class);var result=service.interact(db,area,"ENTER",Map.of("USERID",user,"PASSWD",""));
            var expected=new Commarea(layout,null);expected.set("CDEMO-USER-ID",user.toUpperCase(java.util.Locale.ROOT));
            assertArrayEquals(expected.bytes(),area.bytes());
            assertEquals(user.isEmpty()?"Please enter User ID ...":"Please enter Password ...",result.screen().message);
            verifyNoInteractions(db);
        }
        var area=new Commarea(layout,null);Connection db=mock(Connection.class);
        PreparedStatement q=mock(PreparedStatement.class);ResultSet rs=mock(ResultSet.class);
        when(db.prepareStatement(anyString())).thenReturn(q);when(q.executeQuery()).thenReturn(rs);when(rs.next()).thenReturn(false);
        var result=service.interact(db,area,"ENTER",Map.of("USERID","nobody","PASSWD","wrong"));
        var expected=new Commarea(layout,null);expected.set("CDEMO-USER-ID","NOBODY");
        assertArrayEquals(expected.bytes(),area.bytes());assertEquals("User not found. Try again ...",result.screen().message);
        // A later non-ENTER AID has fresh storage and does not consume input.
        for(String aid:new String[]{"PF1","INITIAL","PF3"}){
            area.set("CDEMO-USER-ID","OLDUSER");service.interact(db,area,aid,Map.of("USERID","ignored"));
            assertArrayEquals(new Commarea(layout,null).bytes(),area.bytes(),aid);
        }
        verify(q,times(1)).executeQuery();
    }
}
