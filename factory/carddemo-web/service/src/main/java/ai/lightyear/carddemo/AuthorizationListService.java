package ai.lightyear.carddemo;

import java.sql.*;
import java.util.*;

/** COPAUS0C orchestration: source paragraphs 178–520, account reads 750–1000. */
public final class AuthorizationListService implements TransactionService {
    private static final String PROGRAM="COPAUS0C",PREFIX="CDEMO-CPVS-";
    private final Bindings b;private final TypedRecords records;private final AuthorizationRecords auth;private final AuthorizationRendering render;
    public AuthorizationListService(Bindings b){this.b=b;records=new TypedRecords(b);auth=new AuthorizationRecords(b);render=new AuthorizationRendering(b);}
    private static boolean blank(String value){return value.chars().allMatch(c->c==' '||c==0);}
    private void message(ScreenFrame f,String text){f.error(b.literal(PROGRAM,text),"ACCTID");}
    private Result next(Commarea a,ScreenFrame f,String target){a.set("CDEMO-TO-PROGRAM",target);a.set("CDEMO-FROM-PROGRAM",PROGRAM);a.set("CDEMO-FROM-TRANID",f.transaction);a.set("CDEMO-PGM-CONTEXT","0");return new Result(target,f,false);}
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input)throws SQLException{return interact(db,area,aid,input,null);}
    @Override public Result interact(Connection db,Commarea area,String aid,Map<String,String> input,ScreenFrame prior)throws SQLException{
        ScreenFrame f=prior==null?new ScreenFrame(b,PROGRAM):prior;
        if(!aid.equals("INITIAL")&&!aid.equals("PF3"))f=receiveFrame(f,input,aid.equals("PF7")||aid.equals("PF8"));
        f.error("","ACCTID");
        f.trace.add(new SourceEdits.Location(b.program(PROGRAM).path("source").asText(),178));
        if(aid.equals("PF3"))return next(area,f,b.program(PROGRAM).path("constants").path("WS-PGM-MENU").asText());
        if(aid.equals("INITIAL")){
            String account=area.get("CDEMO-ACCT-ID");f.set("ACCTID",account);gather(db,area,f,account);
        }else if(aid.equals("ENTER")){
            Map<String,String> values=f.receive(input);String account=values.getOrDefault("ACCTID","");
            // RECEIVE overlay survives the subsequent SEND, including selection characters.
            for(var v:values.entrySet())f.set(v.getKey(),v.getValue());
            area.set(PREFIX+"PAGE-NUM","0");
            if(blank(account)){f.set("ACCTID","");message(f,"Please enter Acct Id...");}
            else if(!account.matches("[0-9]{11}")){f.set("ACCTID","");message(f,"Acct Id must be Numeric ...");}
            else{
                area.set("CDEMO-ACCT-ID",account);String selection="",selected="";
                for(int i=1;i<=5;i++){String value=values.getOrDefault(render.selectionField(i),"");if(!blank(value)){selection=value;selected=area.get(PREFIX+"AUTH-KEYS["+i+"]");break;}}
                area.set(PREFIX+"PAU-SEL-FLG",selection);area.set(PREFIX+"PAU-SELECTED",selected);
                if(!blank(selection)&&!blank(selected)){
                    if(selection.equals("S")||selection.equals("s"))return next(area,f,b.program(PROGRAM).path("constants").path("WS-PGM-AUTH-DTL").asText());
                    message(f,"Invalid selection. Valid value is S");
                }
                gather(db,area,f,account);
            }
        }else if(aid.equals("PF7")){
            int page=Integer.parseInt(area.get(PREFIX+"PAGE-NUM"));
            // RECEIVE replaces ACCTIDL with input length. The top-page branch
            // (COPAUS0C 380-383) sends a message without restoring length -1.
            if(page<=1)f.error(b.literal(PROGRAM,"You are already at the top of the page..."),"");
            else{int previous=page-1;String key=area.get(PREFIX+"PAUKEY-PREV-PG["+previous+"]");area.set(PREFIX+"PAGE-NUM",Integer.toString(previous));
                area.set(PREFIX+"NEXT-PAGE-FLG","Y");
                page(db,area,f,auth.summary(db,area.get("CDEMO-ACCT-ID")),Commarea.encode(key),true);}
        }else if(aid.equals("PF8")){
            if(!area.get(PREFIX+"NEXT-PAGE-FLG").equals("Y"))message(f,"You are already at the bottom of the page...");
            else{String key=area.get(PREFIX+"PAUKEY-LAST");page(db,area,f,auth.summary(db,area.get("CDEMO-ACCT-ID")),blank(key)?null:Commarea.encode(key),false);}
        }else f.error(b.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText(),"ACCTID");
        area.set("CDEMO-PGM-CONTEXT","1");return new Result(PROGRAM,f,false);
    }
    private ScreenFrame receiveFrame(ScreenFrame prior,Map<String,String> input,boolean keepAttributes){
        // COPAU0AI is fresh working storage on each CICS invocation. RECEIVE
        // overlays unprotected input and protected MDT/FSET bytes only. Other
        // text stays blank; POPULATE-HEADER-INFO writes the source headers anew.
        Map<String,String> received=prior.receive(input);ScreenFrame fresh=new ScreenFrame(b,PROGRAM);
        Map<String,String> headers=new LinkedHashMap<>();
        for(var h:b.program(PROGRAM).path("headers")){String name=h.path("target").asText();headers.put(name,fresh.values.get(name));}
        for(String name:fresh.values.keySet()){
            var attributes=prior.attributes.get(name);
            String value=received.get(name);
            if(value==null)value=Boolean.TRUE.equals(attributes.get("modified"))?prior.values.get(name):"";
            fresh.set(name,value);
            if(keepAttributes)fresh.attributes.put(name,new LinkedHashMap<>(attributes));
        }
        headers.forEach(fresh::set);return fresh;
    }
    private void gather(Connection db,Commarea area,ScreenFrame frame,String account)throws SQLException{
        area.set(PREFIX+"PAGE-NUM","0");
        Map<String,Object> xref=records.readByField(db,"cardxref","XREF-ACCT-ID",Commarea.encode(account));
        if(xref==null){missing(frame,"Account:",account," not found in XREF file. Resp:");xref=records.initialized("cardxref");}
        else{area.set("CDEMO-CUST-ID",records.text("cardxref",xref,"XREF-CUST-ID"));area.set("CDEMO-CARD-NUM",records.text("cardxref",xref,"XREF-CARD-NUM"));}
        String accountKey=records.text("cardxref",xref,"XREF-ACCT-ID"),customerKey=records.text("cardxref",xref,"XREF-CUST-ID");
        Map<String,Object> acct=records.read(db,"acctdata",Commarea.encode(accountKey),false);
        if(acct==null){missing(frame,"Account:",accountKey," not found in ACCT file. Resp:");acct=records.initialized("acctdata");}
        Map<String,Object> cust=records.read(db,"custdata",Commarea.encode(customerKey),false);
        if(cust==null){missing(frame,"Customer:",customerKey," not found in CUST file. Resp:");cust=records.initialized("custdata");}
        Map<String,Object> summary=auth.summary(db,account);
        render.account(frame,Map.of("acctdata",acct,"custdata",cust),summary);render.clearRows(frame);
        if(summary!=null)page(db,area,frame,summary,null,false);
    }
    static String stringOverlay(String previous,String prefix){
        int n=Math.min(previous.length(),prefix.length());return prefix.substring(0,n)+previous.substring(n);
    }
    private void missing(ScreenFrame f,String prefix,String key,String text){
        String value=b.literal(PROGRAM,prefix)+key+b.literal(PROGRAM,text)+"000000013"+b.literal(PROGRAM," Reas:")+"000000000";
        // Three consecutive failed reads STRING into the same WS-MESSAGE;
        // a shorter later message retains the previous suffix (COPAUS0C 836-959).
        f.error(stringOverlay(f.values.get("ERRMSG"),value).stripTrailing(),"ACCTID");
    }
    private void page(Connection db,Commarea area,ScreenFrame frame,Map<String,Object> summary,byte[] start,boolean inclusive)throws SQLException{
        List<Map<String,Object>> rows=auth.page(db,summary,start,inclusive,6);render.clearRows(frame);area.set(PREFIX+"PAUKEY-LAST","\u0000".repeat(8));
        int count=Math.min(5,rows.size());
        if(count>0){int page=Integer.parseInt(area.get(PREFIX+"PAGE-NUM"))+1;
            if(page>20)throw new IllegalArgumentException("source-page-history-bound-exceeded");
            area.set(PREFIX+"PAGE-NUM",Integer.toString(page));area.set(PREFIX+"PAUKEY-PREV-PG["+page+"]",new String(AuthorizationRecords.key(rows.get(0)),Commarea.EBCDIC));}
        for(int i=0;i<count;i++){var row=rows.get(i);render.row(frame,i+1,row);String key=new String(AuthorizationRecords.key(row),Commarea.EBCDIC);
            area.set(PREFIX+"AUTH-KEYS["+(i+1)+"]",key);area.set(PREFIX+"PAUKEY-LAST",key);}
        if(count==5)area.set(PREFIX+"NEXT-PAGE-FLG",rows.size()>5?"Y":"N");
    }
}
