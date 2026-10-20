package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;

/** COPAUS1C dispatch, qualified GNP, next-detail and linked fraud transaction. */
public final class AuthorizationDetailService implements TransactionService {
    private static final String PROGRAM="COPAUS1C",SELECTED="CDEMO-CPVD-PAU-SELECTED";
    private final Bindings b;private final AuthorizationRecords records;private final AuthorizationRendering render;private final AuthorizationFraud fraud;
    public AuthorizationDetailService(Bindings b){this.b=b;records=new AuthorizationRecords(b);render=new AuthorizationRendering(b);fraud=new AuthorizationFraud(b);}
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input)throws SQLException{return interact(db,area,aid,input,null);}
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input,ScreenFrame prior)throws SQLException{
        ScreenFrame frame=new ScreenFrame(b,PROGRAM);frame.cursor="CARDNUM";area.set("CDEMO-CPVD-FRAUD-DATA","");
        frame.trace.add(new SourceEdits.Location(b.program(PROGRAM).path("source").asText(),157));
        if(aid.equals("PF3")){
            String next=b.program(PROGRAM).path("constants").path("WS-PGM-AUTH-SMRY").asText();
            area.set("CDEMO-TO-PROGRAM",next);area.set("CDEMO-FROM-PROGRAM",PROGRAM);area.set("CDEMO-FROM-TRANID",frame.transaction);area.set("CDEMO-PGM-CONTEXT","0");return new Result(next,frame,false);
        }
        if(prior!=null)prior.receive(input); // Protected detail fields cannot be supplied by the client.
        String selected=area.get(SELECTED);boolean valid=!selected.chars().allMatch(c->c==0||c==' ');
        if(valid){
            var parent=records.summary(db,area.get("CDEMO-ACCT-ID"));byte[] key=Commarea.encode(selected);
            var detail=records.detail(db,parent,key,aid.equals("PF5"));
            if(aid.equals("PF8")){
                var next=records.page(db,parent,key,false,1);
                if(next.isEmpty()){
                    if(prior!=null)frame=prior;frame.error(b.literal(PROGRAM,"Already at the last Authorization..."),"CARDNUM");
                }else{detail=next.get(0);area.set(SELECTED,new String(AuthorizationRecords.key(detail),Commarea.EBCDIC));render.detail(frame,detail);}
            }else if(aid.equals("PF5")){
                // A missing qualified detail cannot be rewritten. Native error-path proof remains explicit.
                if(detail==null)throw new IllegalArgumentException("source-selected-authorization-not-found");
                Savepoint save=db.setSavepoint();
                try{detail=fraud.apply(db,area,detail);db.releaseSavepoint(save);render.detail(frame,detail);
                    boolean removed=new TypedRecords(b).text("pautdtl1",detail,"PA-AUTH-FRAUD").equals("R");frame.error(b.literal(PROGRAM,removed?"AUTH FRAUD REMOVED...":"AUTH MARKED FRAUD..."),"CARDNUM");
                }catch(SQLException failure){db.rollback(save);throw failure;}
            }else if(detail!=null)render.detail(frame,detail);
            else render.detail(frame,new TypedRecords(b).initialized("pautdtl1"));
        }
        if(!Set.of("INITIAL","ENTER","PF5","PF8").contains(aid))frame.error(b.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText(),"CARDNUM");
        area.set("CDEMO-PGM-CONTEXT","1");return new Result(PROGRAM,frame,false);
    }
}
