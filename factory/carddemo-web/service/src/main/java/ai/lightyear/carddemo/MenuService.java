package ai.lightyear.carddemo;

import java.sql.Connection;
import java.util.Map;
import tools.jackson.databind.JsonNode;

/** COMEN01C lines 73-305. Menu contents and access roles are source-generated. */
public final class MenuService implements TransactionService {
    private final Bindings bindings;
    public MenuService(Bindings bindings){this.bindings=bindings;}
    public Result interact(Connection db,Commarea area,String aid,Map<String,String> input){
        ScreenFrame frame=new ScreenFrame(bindings,"COMEN01C");
        for(JsonNode option:bindings.root.path("menu")){
            int number=option.path("number").asInt();
            // 260-304: output field name comes from generated menu move bindings.
            String field=bindings.root.path("menu_outputs").path(Integer.toString(number)).asText();
            if(field.isEmpty())throw new IllegalArgumentException("menu-output-unbound");
            frame.set(field,String.format(java.util.Locale.ROOT,"%02d. %s",number,option.path("label").asText()));
        }
        if(aid.equals("INITIAL")){
            // COMEN01C 86-90 sets REENTER before the first SEND/RETURN.
            area.set("CDEMO-PGM-CONTEXT","1");return new Result("COMEN01C",frame,false);
        }
        // COMEN01C receives before EVALUATE EIBAID, even for an invalid PF key.
        String inputOption=frame.receive(input).get("OPTION");frame.set("OPTION",inputOption);
        if(aid.equals("PF3"))return new Result("COSGN00C",frame,false); // 94-95
        if(!aid.equals("ENTER")){frame.error(bindings.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText().stripTrailing(),frame.cursor);return new Result("COMEN01C",frame,false);}
        // Source trims trailing spaces, then pads WS-OPTION-X and replaces every space with zero.
        String value=inputOption.replaceFirst(" +$","");
        int width=bindings.root.path("menu_option_width").asInt();
        value=(" ".repeat(Math.max(0,width-value.length()))+value).replace(' ','0');
        // Source MOVE WS-OPTION TO OPTIONO precedes the numeric/range validation.
        frame.set("OPTION",value);
        if(!value.matches("[0-9]+"))return invalid(frame);
        int number=Integer.parseInt(value);JsonNode options=bindings.root.path("menu");
        if(number<1 || number>options.size())return invalid(frame); // 129-136
        JsonNode selected=options.get(number-1);
        frame.set("OPTION",value);
        if(area.get("CDEMO-USER-TYPE").equals("U") && selected.path("role").asText().equals("A")){
            frame.error(bindings.literal("COMEN01C","No access - Admin Only option... "),frame.cursor);return new Result("COMEN01C",frame,false); // 139-145
        }
        area.set("CDEMO-FROM-TRANID",frame.transaction);area.set("CDEMO-FROM-PROGRAM",frame.program);area.set("CDEMO-PGM-CONTEXT","0");
        if(!selected.path("in_slice").asBoolean())frame.endpoint=bindings.root.path("outside_endpoint").asText();
        return new Result(selected.path("program").asText(),frame,false);
    }
    private Result invalid(ScreenFrame frame){frame.error(bindings.literal("COMEN01C","Please enter a valid option number..."),frame.cursor);return new Result("COMEN01C",frame,false);}
}
