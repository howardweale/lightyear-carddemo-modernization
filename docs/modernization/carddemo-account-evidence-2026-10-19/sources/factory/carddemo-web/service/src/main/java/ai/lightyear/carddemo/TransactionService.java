package ai.lightyear.carddemo;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Map;

public interface TransactionService {
    record Result(String nextProgram,ScreenFrame screen,boolean ended) {}
    Result interact(Connection database,Commarea commarea,String aid,Map<String,String> input)throws SQLException;
    default Result interact(Connection database,Commarea commarea,String aid,Map<String,String> input,ScreenFrame prior)throws SQLException {
        return interact(database,commarea,aid,input);
    }
}
