package ai.lightyear.carddemo;

import java.nio.file.Path;
import java.sql.*;
import java.time.*;
import java.util.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import tools.jackson.databind.json.JsonMapper;

class InteractionEngineTest {
    private Bindings bindings()throws Exception{Path root=Path.of(System.getProperty("carddemo.root"));
        return new Bindings(root.resolve("work/carddemo-web-bindings/bindings.json"),root.resolve("work/carddemo-web-data/plan.json"),JsonMapper.builder().build());}
    private SessionToken tokens(Bindings b){return new SessionToken(new byte[32],b.hash,Clock.fixed(Instant.parse("2026-10-17T12:34:56Z"),ZoneOffset.UTC),JsonMapper.builder().build());}
    @Test void xctlUsesOneTransactionAndPrivateAreaIsReturnedInToken()throws Exception{
        Bindings b=bindings();SessionToken token=tokens(b);DataSource ds=mock(DataSource.class);Connection c=mock(Connection.class);when(ds.getConnection()).thenReturn(c);
        TransactionService first=(db,area,aid,input)->{assertSame(c,db);area.set("CDEMO-USER-ID","TESTUSER");return new TransactionService.Result("COACTVWC",new ScreenFrame(b,"COSGN00C"),false);};
        TransactionService next=(db,area,aid,input)->{assertSame(c,db);assertEquals("INITIAL",aid);assertEquals("TESTUSER",area.get("CDEMO-USER-ID"));assertEquals(2000,area.bytes().length);return new TransactionService.Result("COACTVWC",new ScreenFrame(b,"COACTVWC"),false);};
        var result=new InteractionEngine(b,token,ds,Map.of("COSGN00C",first,"COACTVWC",next)).interact(new InteractionEngine.Request(null,"INITIAL",Map.of()));
        assertEquals("COACTVWC",token.verify(result.token()).program());assertEquals(2000,Base64.getDecoder().decode(token.verify(result.token()).commarea()).length);
        verify(ds,times(1)).getConnection();verify(c,times(1)).commit();verify(c,never()).rollback();verify(c).close();
    }
    @Test void handlerFailureRollsBackAndForgedSessionNeverOpensConnection()throws Exception{
        Bindings b=bindings();DataSource ds=mock(DataSource.class);Connection c=mock(Connection.class);when(ds.getConnection()).thenReturn(c);
        TransactionService failure=(db,area,aid,input)->{throw new SQLException("fixture failure after write");};
        var engine=new InteractionEngine(b,tokens(b),ds,Map.of("COSGN00C",failure));
        assertThrows(SQLException.class,()->engine.interact(new InteractionEngine.Request(null,"INITIAL",Map.of())));
        verify(c).rollback();verify(c,never()).commit();verify(c).close();clearInvocations(ds);
        assertThrows(IllegalArgumentException.class,()->engine.interact(new InteractionEngine.Request("forged.signature","ENTER",Map.of())));verifyNoInteractions(ds);
        assertThrows(IllegalArgumentException.class,()->engine.interact(new InteractionEngine.Request(null,"ENTER",Map.of())));verifyNoInteractions(ds);
    }
    @Test void deterministicHeaderComesFromPinnedMovesAndClock()throws Exception{
        Bindings b=bindings();ScreenFrame frame=new ScreenFrame(b,"COACTVWC",Clock.fixed(Instant.parse("2026-10-17T12:34:56Z"),ZoneOffset.UTC));
        assertEquals("10/17/26",frame.values.get("CURDATE"));assertEquals("12:34:56",frame.values.get("CURTIME"));
        assertEquals("COACTVWC",frame.values.get("PGMNAME"));assertEquals("CAVW",frame.values.get("TRNNAME"));
    }
}
