package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;
import javax.sql.DataSource;

/** One database transaction per interaction, including every translated XCTL. */
public final class InteractionEngine {
    public record Request(String token,String aid,Map<String,String> fields){}
    public record Response(String token,ScreenFrame screen,boolean ended,String sourceHash){}
    private final Bindings bindings;private final SessionToken tokens;private final DataSource database;
    private final Map<String,TransactionService> services;
    public InteractionEngine(Bindings bindings,SessionToken tokens,DataSource database,Map<String,TransactionService> services){
        this.bindings=bindings;this.tokens=tokens;this.database=database;this.services=Map.copyOf(services);
    }
    public Response interact(Request request)throws SQLException {
        if(request==null||request.aid()==null||!request.aid().matches("INITIAL|ENTER|PF(?:[1-9]|1[0-9]|2[0-4])"))throw new IllegalArgumentException("interaction-aid");
        Map<String,String> input=request.fields()==null?Map.of():request.fields();
        if(input.size()>100)throw new IllegalArgumentException("interaction-field-count");
        String program;Commarea area;ScreenFrame prior=null;
        if(request.token()==null||request.token().isEmpty()){
            if(!request.aid().equals("INITIAL")||!input.isEmpty())throw new IllegalArgumentException("session-required");
            program="COSGN00C";area=new Commarea(bindings.root.path("program_commareas").path(program),null);
        }else{
            var state=tokens.verify(request.token());program=state.program();
            area=new Commarea(bindings.root.path("program_commareas").path(program),Base64.getDecoder().decode(state.commarea()));
            if(state.terminal()!=null){prior=new ScreenFrame(bindings,program);prior.restore(state.terminal());}
        }
        String aid=request.aid();
        try(Connection connection=database.getConnection()){
            connection.setAutoCommit(false);
            try{
                TransactionService.Result result=null;
                for(int depth=0;depth<8;depth++){
                    TransactionService service=services.get(program);
                    if(service==null)throw new UnsupportedOperationException("slice-handler-not-yet-implemented:"+program);
                    result=service.interact(connection,area,aid,input,prior);
                    if(result.ended()||result.nextProgram().equals(program)||!result.screen().endpoint.isEmpty())break;
                    String next=result.nextProgram();
                    if(!bindings.root.path("program_commareas").has(next)){
                        // Admin sign-on and menu targets outside the six screens share one explicit boundary.
                        result.screen().endpoint=bindings.root.path("outside_endpoint").asText();break;
                    }
                    boolean ims=Set.of("COPAUS0C","COPAUS1C").contains(program)&&Set.of("COPAUS0C","COPAUS1C").contains(next);
                    area=area.transition(bindings.root.path("program_commareas").path(next),bindings.root.path("commarea").path("record_length").asInt(),ims);
                    program=next;aid="INITIAL";input=Map.of();prior=null;result=null;
                }
                if(result==null)throw new IllegalStateException("xctl-depth-limit");
                String nextToken=result.ended()?null:tokens.issue(program,area.bytes(),result.screen());
                // Serialize/token failure must also roll back, before committing any interaction write.
                Response response=new Response(nextToken,result.screen(),result.ended(),bindings.hash);connection.commit();return response;
            }catch(SQLException|RuntimeException failure){
                try{connection.rollback();}catch(SQLException rollback){failure.addSuppressed(rollback);}throw failure;
            }
        }
    }
}
