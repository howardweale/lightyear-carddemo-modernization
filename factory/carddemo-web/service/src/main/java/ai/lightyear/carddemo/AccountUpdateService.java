package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;

/** COACTUPC transaction orchestration. Editing, messages and rendering execute
 * generated source statements; physical data columns always come from the plan.
 * Source ranges: main 903â€“1009, action 2561â€“2647, reads 3608â€“3797, write 3892â€“4106.
 */
public final class AccountUpdateService implements TransactionService {
    private static final String PROGRAM="COACTUPC";
    private final Bindings bindings;private final TypedRecords records;private final AccountUpdateTransaction update;
    public AccountUpdateService(Bindings b){bindings=b;records=new TypedRecords(b);update=new AccountUpdateTransaction(b);}
    private SourceEdits edits(Commarea area){SourceEdits e=new SourceEdits(AccountRenderModel.retire(bindings.root.path("account_update").path("validation")),bindings.clock);e.loadArea(area);return e;}
    private String literal(String value){return bindings.literal(PROGRAM,value);}
    private static boolean blank(String text){return text.chars().allMatch(c->c==0||c==' ');}
    @CobolSource(program="COACTUPC", paragraph="COMMON-RETURN", lines="1007-1020")
    @CobolSource(program="COACTUPC", paragraph="3000-SEND-MAP", lines="2649-2663")
    @CobolSource(program="COACTUPC", paragraph="3100-SCREEN-INIT", lines="2668-2693")
    @CobolSource(program="COACTUPC", paragraph="3400-SEND-SCREEN", lines="3589-3602")
    private Result render(Commarea area,SourceEdits e){
        ScreenFrame screen=new ScreenFrame(bindings,PROGRAM);e.attachScreen(screen);
        for(String paragraph:List.of("3200-SETUP-SCREEN-VARS","3250-SETUP-INFOMSG","3300-SETUP-SCREEN-ATTRS","3390-SETUP-INFOMSG-ATTRS"))e.run(paragraph);
        e.setCondition("CDEMO-PGM-REENTER");e.saveArea(area);screen.trace.addAll(e.trace());return new Result(PROGRAM,screen,false);
    }
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input)throws SQLException{
        return interact(db,area,aid,input,null);
    }
    @CobolSource(program="COACTUPC", paragraph="0000-MAIN", lines="859-1006")
    @CobolSource(program="COACTUPC", paragraph="1000-PROCESS-INPUTS", lines="1025-1035")
    @CobolSource(program="COACTUPC", paragraph="2000-DECIDE-ACTION", lines="2562-2642")
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input,ScreenFrame prior)throws SQLException{
        // Source maps invalid PF keys to ENTER. PF3 precedes every other state.
        if(aid.equals("PF3")){
            String previous=area.get("CDEMO-FROM-PROGRAM"),transaction=area.get("CDEMO-FROM-TRANID");
            if(blank(previous))previous=bindings.program(PROGRAM).path("constants").path("LIT-MENUPGM").asText();
            if(blank(transaction))transaction=bindings.program(PROGRAM).path("constants").path("LIT-MENUTRANID").asText();
            area.set("CDEMO-TO-PROGRAM",previous);area.set("CDEMO-TO-TRANID",transaction);
            area.set("CDEMO-FROM-PROGRAM",PROGRAM);area.set("CDEMO-FROM-TRANID",bindings.screen(PROGRAM).path("transaction").asText());
            area.set("CDEMO-USER-TYPE","U");area.set("CDEMO-PGM-CONTEXT","0");
            area.move("CDEMO-LAST-MAPSET",bindings.program(PROGRAM).path("constants").path("LIT-THISMAPSET").asText());
            area.move("CDEMO-LAST-MAP",bindings.program(PROGRAM).path("constants").path("LIT-THISMAP").asText());
            return new Result(previous.stripTrailing(),new ScreenFrame(bindings,PROGRAM),false);
        }
        String state=area.get("ACUP-CHANGE-ACTION");
        if(aid.equals("INITIAL")||Set.of("C","L","F").contains(state)){
            // Preserve the caller's common prefix, reset only this program's tail.
            Commarea fresh=new Commarea(bindings.root.path("program_commareas").path(PROGRAM),null);
            int common=bindings.root.path("commarea").path("record_length").asInt();
            area.copyBytes(common,Arrays.copyOfRange(fresh.bytes(),common,fresh.bytes().length));
            area.set("CDEMO-ACCT-ID","0");area.set("CDEMO-PGM-CONTEXT","0");
            SourceEdits e=edits(area);e.setCondition("ACUP-DETAILS-NOT-FETCHED");return render(area,e);
        }
        if(prior==null||!prior.program.equals(PROGRAM))throw new IllegalArgumentException("account-terminal-required");
        boolean cancel=aid.equals("PF12")&&!blank(state),confirm=aid.equals("PF5")&&state.equals("N");
        SourceEdits e=edits(area);e.attachScreen(prior);e.receiveScreen(input);e.run("1100-RECEIVE-MAP");e.run("1200-EDIT-MAP-INPUTS");e.saveArea(area);
        // 2000-DECIDE-ACTION evaluates the state AFTER source input edits.
        if(e.condition("ACUP-DETAILS-NOT-FETCHED")||cancel){
            if(e.condition("FLG-ACCTFILTER-ISVALID")){e.setCondition("WS-RETURN-MSG-OFF");fetch(db,area,e);if(e.condition("FOUND-CUST-IN-MASTER"))e.setCondition("ACUP-SHOW-DETAILS");}
        }else if(e.condition("ACUP-SHOW-DETAILS")){
            if(!e.condition("INPUT-ERROR")&&!e.condition("NO-CHANGES-DETECTED"))e.setCondition("ACUP-CHANGES-OK-NOT-CONFIRMED");
        }else if(e.condition("ACUP-CHANGES-OK-NOT-CONFIRMED")&&confirm){
            e.saveArea(area);Savepoint savepoint=db.setSavepoint();
            try{
                switch(update.save(db,area)){
                    case UPDATED_PENDING_COMMIT:e.setCondition("ACUP-CHANGES-OKAYED-AND-DONE");break;
                    case CONFLICT:e.setCondition("DATA-WAS-CHANGED-BEFORE-UPDATE");e.setCondition("ACUP-SHOW-DETAILS");break;
                    case ACCOUNT_NOT_FOUND:e.setCondition("COULD-NOT-LOCK-ACCT-FOR-UPDATE");e.setCondition("ACUP-CHANGES-OKAYED-LOCK-ERROR");break;
                    // Source only tests the account-lock 88 in 2000. Keep its customer-lock quirk visible.
                    case CUSTOMER_NOT_FOUND:e.setCondition("COULD-NOT-LOCK-CUST-FOR-UPDATE");e.setCondition("ACUP-CHANGES-OKAYED-AND-DONE");break;
                }
                db.releaseSavepoint(savepoint);
            }catch(SQLException failure){
                db.rollback(savepoint);e.setCondition("LOCKED-BUT-UPDATE-FAILED");e.setCondition("ACUP-CHANGES-OKAYED-BUT-FAILED");
            }
        }
        return render(area,e);
    }
    @CobolSource(program="COACTUPC", paragraph="9000-READ-ACCT", lines="3608-3646")
    @CobolSource(program="COACTUPC", paragraph="9200-GETCARDXREF-BYACCT", lines="3650-3697")
    @CobolSource(program="COACTUPC", paragraph="9300-GETACCTDATA-BYACCT", lines="3701-3747")
    @CobolSource(program="COACTUPC", paragraph="9400-GETCUSTDATA-BYCUST", lines="3752-3796")
    private void fetch(Connection db,Commarea area,SourceEdits e)throws SQLException{
        String account=e.get("CC-ACCT-ID");area.initialize("ACUP-OLD-DETAILS");e.setCondition("WS-NO-INFO-MESSAGE");
        area.move("ACUP-OLD-ACCT-ID",account); // COACTUPC 3614: retain search key even when the xref READ fails.
        Map<String,Object> cross=records.readByField(db,"cardxref","XREF-ACCT-ID",Commarea.encode(account));
        if(cross==null){missing(e,account," Cross ref file.  Resp:",false);e.loadArea(area);return;}
        String customer=records.text("cardxref",cross,"XREF-CUST-ID");
        area.set("CDEMO-CUST-ID",customer);area.set("CDEMO-CARD-NUM",records.text("cardxref",cross,"XREF-CARD-NUM"));
        Map<String,Object> acct=records.read(db,"acctdata",Commarea.encode(account),false);
        if(acct==null)missing(e,account," Acct Master file.Resp:",false);else e.setCondition("FOUND-ACCT-IN-MASTER");
        // The source's missing-record 88 literals differ from its assembled messages.
        // Therefore the customer read and STORE-FETCHED-DATA still execute.
        Map<String,Object> cust=records.read(db,"custdata",Commarea.encode(customer),false);
        if(cust==null)missing(e,customer," in customer master.Resp: ",true);else e.setCondition("FOUND-CUST-IN-MASTER");
        update.capture(area,Map.of("cardxref",cross,"acctdata",acct==null?records.initialized("acctdata"):acct,"custdata",cust==null?records.initialized("custdata"):cust));
        e.loadArea(area);
    }
    private void missing(SourceEdits e,String key,String file,boolean customer){
        e.setCondition("INPUT-ERROR");e.setCondition(customer?"FLG-CUSTFILTER-NOT-OK":"FLG-ACCTFILTER-NOT-OK");
        if(!e.condition("WS-RETURN-MSG-OFF"))return;
        String value=customer?literal("CustId:")+key+literal(" not found")+literal(file)+"000000013 "+literal(" REAS:")+"000000000 ":literal("Account:")+key+literal(" not found in")+literal(file)+"000000013 "+literal(" Reas:")+"000000000 ";
        e.put("WS-RETURN-MSG",value);
    }
}
