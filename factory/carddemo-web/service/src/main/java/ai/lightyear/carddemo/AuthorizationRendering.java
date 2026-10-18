package ai.lightyear.carddemo;

import java.util.*;
import tools.jackson.databind.JsonNode;

/** Execute only source-compiled render statements. No manually maintained field map. */
public final class AuthorizationRendering {
    private final Bindings b;private final AuthorizationRecords records;
    public AuthorizationRendering(Bindings bindings){b=bindings;records=new AuthorizationRecords(b);}
    public SourceEdits edits(String program,ScreenFrame frame){
        SourceEdits e=new SourceEdits(b.root.path("authorization").path(program),b.clock);e.attachScreen(frame);e.setCondition("ERR-FLG-OFF");return e;
    }
    public String selectionField(int ordinal){
        for(JsonNode stmt:b.root.path("authorization").path("COPAUS0C").path("paragraphs").path("ROW-"+ordinal))
            if(stmt.path("op").asText().equals("move")&&stmt.path("value").path("name").asText().equals("DFHBMUNP")){
                String symbol=stmt.path("targets").get(0).path("name").asText();return symbol.substring(0,symbol.length()-1);}
        throw new IllegalArgumentException("source-row-selection-missing");
    }
    public void clearRows(ScreenFrame frame){
        JsonNode model=b.root.path("authorization").path("COPAUS0C");
        for(int i=1;i<=5;i++)for(JsonNode move:model.path("paragraphs").path("ROW-"+i))for(JsonNode target:move.path("targets")){
            JsonNode f=model.path("fields").path(target.path("name").asText());String name=f.path("screen_field").asText();
            if(name.isEmpty())continue;
            if(f.path("screen_part").asText().equals("A")){frame.attributes.get(name).put("protected",true);frame.attributes.get(name).put("modified",false);}
            else frame.set(name,"");
        }
    }
    public void row(ScreenFrame frame,int ordinal,Map<String,Object> row){
        JsonNode model=b.root.path("authorization").path("COPAUS0C");SourceEdits e=edits("COPAUS0C",frame);
        records.load(e,model,"pautdtl1",row);e.run("ROW-PREFIX");e.run("ROW-"+ordinal);frame.trace.addAll(e.trace());
    }
    public void account(ScreenFrame frame,Map<String,Map<String,Object>> rows,Map<String,Object> summary){
        JsonNode model=b.root.path("authorization").path("COPAUS0C");SourceEdits e=edits("COPAUS0C",frame);
        for(var entry:rows.entrySet())records.load(e,model,entry.getKey(),entry.getValue());
        if(summary!=null){records.load(e,model,"pautsum0",summary);e.setCondition("FOUND-PAUT-SMRY-SEG");}
        else e.put(model.path("conditions").path("FOUND-PAUT-SMRY-SEG").path("parent").asText(),"N");
        e.run("GATHER-ACCOUNT-DETAILS");frame.trace.addAll(e.trace());
    }
    public void detail(ScreenFrame frame,Map<String,Object> row){
        JsonNode model=b.root.path("authorization").path("COPAUS1C");SourceEdits e=edits("COPAUS1C",frame);
        records.load(e,model,"pautdtl1",row);e.run("POPULATE-AUTH-DETAILS");frame.trace.addAll(e.trace());
    }
}
