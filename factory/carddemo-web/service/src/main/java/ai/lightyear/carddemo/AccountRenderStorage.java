package ai.lightyear.carddemo;
import java.math.BigDecimal;
import static ai.lightyear.carddemo.AccountRenderState.*;
/** Uses the existing fixed-width moves, edited currency and BMS write primitives. */
public final class AccountRenderStorage implements AccountRenderState {
    private final SourceEdits edits;
    public AccountRenderStorage(SourceEdits edits){this.edits=edits;}
    private static String name(Enum<?> value){return value.name().replace('_','-');}
    public void move(ScreenField target,Value source){edits.mapMove(target.name()+"O",name(source));}
    public void move(Value target,Value source){edits.mapMove(name(target),name(source));}
    public void slice(ScreenField target,Value source,int start,int length){edits.put(target.name()+"O",edits.get(name(source)).substring(start-1,start-1+length));}
    public void low(ScreenField field){edits.mapLow(field.name()+"O");}
    public void text(ScreenField field,String text){edits.put(field.name()+"O",text);}
    public void cursor(ScreenField field){edits.put(field.name()+"L","-1");}
    public void attribute(ScreenField field,Attribute attribute){edits.put(field.name()+"A",attribute.name());}
    public void color(ScreenField field,Color color){edits.put(field.name()+"C",color.name());}
    public boolean test(Flag flag){return edits.condition(name(flag));}
    public void set(Flag flag){edits.setCondition(name(flag));}
    public boolean bad(Edit edit){return edits.condition("FLG-"+name(edit)+"-NOT-OK");}
    public boolean blank(Edit edit){return edits.condition("FLG-"+name(edit)+"-BLANK");}
    public boolean valid(Edit edit){return edits.condition("FLG-"+name(edit)+"-ISVALID");}
    public boolean accountZero(){
        String value=edits.get("CC-ACCT-ID-N");
        return value.matches("[+-]?[0-9]+(?:[.][0-9]+)?") && new BigDecimal(value).compareTo(BigDecimal.ZERO)==0;
    }
    public boolean fromCardList(){return edits.mapSame("CDEMO-LAST-MAPSET","LIT-CCLISTMAPSET");}
    public void clearNonKeyFlags(){edits.mapLow("WS-NON-KEY-FLAGS");}
}
