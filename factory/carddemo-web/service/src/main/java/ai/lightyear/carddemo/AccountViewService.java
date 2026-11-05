package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;

/** COACTVWC: physical source lines below are checked against the pinned bindings. */
public final class AccountViewService implements TransactionService {
    private static final String PROGRAM="COACTVWC";
    private final Bindings bindings;private final TypedRecords records;private final AccountViewRendering projection;private final AccountViewConstants constants;
    public AccountViewService(Bindings bindings){this.bindings=bindings;records=new TypedRecords(bindings);projection=new AccountViewRendering(bindings);constants=AccountViewConstants.load(bindings);CommonArea.validateLayout(bindings.root.path("program_commareas").path(PROGRAM));}
    private String message(String value){return bindings.literal(PROGRAM,value);}
    @CobolSource(program="COACTVWC", paragraph="0000-MAIN", lines="262-393")
    public Result interact(Connection db,Commarea area,String aid,Map<String,String> input)throws SQLException {
        CommonArea common=new CommonArea(area);
        ScreenFrame frame=new ScreenFrame(bindings,PROGRAM);frame.cursor="ACCTSID";
        frame.set("INFOMSG",message("Enter or update id of account to display")); // 113–114,528–534
        frame.attributes.get("INFOMSG").put("color","NEUTRAL");
        // 543: DFHBMFSE is unprotected normal with modified-data-tag set.
        frame.attributes.get("ACCTSID").put("modified",true);
        if(aid.equals("PF3")){ // 324–350
            String previous=common.get(CommonArea.Field.PREVIOUS_PROGRAM),transaction=common.get(CommonArea.Field.PREVIOUS_TRANSACTION);
            if(empty(previous))previous=constants.menuProgram();
            if(empty(transaction))transaction=constants.menuTransaction();
            common.set(CommonArea.Field.NEXT_PROGRAM,previous);common.set(CommonArea.Field.NEXT_TRANSACTION,transaction);
            common.set(CommonArea.Field.PREVIOUS_PROGRAM,PROGRAM);common.set(CommonArea.Field.PREVIOUS_TRANSACTION,frame.transaction);
            common.set(CommonArea.Field.USER_TYPE,"U");common.set(CommonArea.Field.PROGRAM_CONTEXT,"0");
            common.move(CommonArea.Field.LAST_MAPSET,constants.mapset());
            common.move(CommonArea.Field.LAST_MAP,constants.map());
            return new Result(previous.stripTrailing(),frame,false);
        }
        common.set(CommonArea.Field.PROGRAM_CONTEXT,"1"); // 581; other PF keys are mapped to ENTER at 306–314.
        if(aid.equals("INITIAL"))return new Result(PROGRAM,frame,false);
        String account=frame.receive(input).get("ACCTSID"); // 628–642,653–679
        if(account.equals(ScreenFrame.pad("*",account.length())) || empty(account)){
            common.set(CommonArea.Field.ACCOUNT_ID,"0");frame.set("ACCTSID","*");return error(frame,"No input received");}
        frame.set("ACCTSID",account);
        if(!account.matches("[0-9]{11}") || account.equals("00000000000")){
            common.set(CommonArea.Field.ACCOUNT_ID,"0");return error(frame,"Account Filter must  be a non-zero 11 digit number");}
        common.set(CommonArea.Field.ACCOUNT_ID,account);
        // 9000/9200: XREF alternate account path is read before either master.
        var xref=records.readByField(db,"cardxref","XREF-ACCT-ID",Commarea.encode(account));
        if(xref==null)return missing(frame,account," Cross ref file.  Resp:");
        String customer=records.text("cardxref",xref,"XREF-CUST-ID");
        common.set(CommonArea.Field.CUSTOMER_ID,customer);common.set(CommonArea.Field.CARD_NUMBER,records.text("cardxref",xref,"XREF-CARD-NUM"));
        var acct=records.read(db,"acctdata",Commarea.encode(account),false);
        if(acct==null)missing(frame,account," Acct Master file.Resp:");
        // 704 tests an 88 literal different from the constructed error text, so customer READ still occurs.
        // Keep this source quirk visible; the independent reference must exercise it.
        Map<String,Map<String,Object>> rows=new LinkedHashMap<>();if(acct!=null)rows.put("acctdata",acct);
        var cust=records.read(db,"custdata",Commarea.encode(customer),false);if(cust!=null)rows.put("custdata",cust);
        if(acct==null && cust!=null)rows.put("acctdata",records.initialized("acctdata")); // Explicit deterministic uninitialized-record reference assumption.
        projection.apply(frame,rows.get("acctdata"),rows.get("custdata")); // 471–523
        if(cust==null && frame.message.isEmpty()){ // 9400: master data already read is still displayed.
            String reason=message("CustId:")+customer+message(" not found")+message(" in customer master.Resp: ")+response(13)+message(" REAS:")+response(0);
            frame.error(ScreenFrame.pad(reason,75).stripTrailing(),frame.cursor);return new Result(PROGRAM,frame,false);
        }
        return new Result(PROGRAM,frame,false);
    }
    private Result error(ScreenFrame frame,String value){frame.error(message(value),"ACCTSID");frame.attributes.get("ACCTSID").put("color","RED");return new Result(PROGRAM,frame,false);}
    private Result missing(ScreenFrame frame,String account,String file){
        frame.error(ScreenFrame.pad(message("Account:")+account+message(" not found in")+message(file)+response(13)+message(" Reas:")+response(0),75).stripTrailing(),"ACCTSID");
        frame.attributes.get("ACCTSID").put("color","RED");return new Result(PROGRAM,frame,false);
    }
    // Signed S9(9) COMP to PIC X(10): nine display digits, then right space padding.
    private String response(int value){return String.format(Locale.ROOT,"%09d ",value);}
    private boolean empty(String value){return value.chars().allMatch(c->c==' ') || value.chars().allMatch(c->c==0);}
}
