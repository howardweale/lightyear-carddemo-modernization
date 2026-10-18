package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;

/** Translation of COSGN00C, physical lines 73â€“265 at the bound source hash. */
public final class SignonService implements TransactionService {
    private final Bindings bindings;private final TypedRecords records;
    public SignonService(Bindings bindings){this.bindings=bindings;this.records=new TypedRecords(bindings);}
    public Result interact(Connection db,Commarea area,String aid,Map<String,String> input)throws SQLException {
        ScreenFrame frame=new ScreenFrame(bindings,"COSGN00C");
        if(aid.equals("INITIAL"))return new Result("COSGN00C",frame,false); // lines 80â€“83
        if(aid.equals("PF3")){frame.message=bindings.root.path("common_constants").path("CCDA-MSG-THANK-YOU").asText().stripTrailing();return new Result("COSGN00C",frame,true);} // 88â€“90; caller renders bound CCDA-MSG-THANK-YOU
        if(!aid.equals("ENTER")){frame.error(bindings.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText().stripTrailing(),frame.cursor);return new Result("COSGN00C",frame,false);}
        Map<String,String> received=frame.receive(input);
        // RECEIVE writes the shared BMS input/output area; error SEND preserves the received values.
        received.forEach(frame::set);
        String user=received.get("USERID"),password=received.get("PASSWD");
        // Lines 121â€“130: all spaces / all low-values, not trim/blank Unicode rules.
        if(empty(user))return error(frame,"Please enter User ID ...","USERID");
        if(empty(password))return error(frame,"Please enter Password ...","PASSWD");
        user=user.toUpperCase(Locale.ROOT);password=password.toUpperCase(Locale.ROOT); // 137â€“142
        Map<String,Object> row=records.read(db,"usrsec",Commarea.encode(user),false);
        if(row==null)return error(frame,"User not found. Try again ...","USERID"); // 253â€“257
        if(!records.text("usrsec",row,"SEC-USR-PWD").equals(password))return error(frame,"Wrong Password. Try again ...","PASSWD"); // 244â€“249
        area.set("CDEMO-FROM-TRANID",frame.transaction);area.set("CDEMO-FROM-PROGRAM",frame.program);
        area.set("CDEMO-USER-ID",user);area.set("CDEMO-USER-TYPE",records.text("usrsec",row,"SEC-USR-TYPE"));area.set("CDEMO-PGM-CONTEXT","0"); // 223â€“227
        return new Result(area.get("CDEMO-USER-TYPE").equals("A")?"COADM01C":"COMEN01C",frame,false); // 229â€“240
    }
    private boolean empty(String value){return value.chars().allMatch(c->c==' ') || value.chars().allMatch(c->c==0);}
    private Result error(ScreenFrame frame,String message,String cursor){frame.error(bindings.literal("COSGN00C",message),cursor);return new Result("COSGN00C",frame,false);}
}
