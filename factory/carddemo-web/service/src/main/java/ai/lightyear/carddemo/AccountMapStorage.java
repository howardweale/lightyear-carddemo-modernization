package ai.lightyear.carddemo;

import static ai.lightyear.carddemo.AccountMapState.*;

/** Fixed-width storage adaptation, with no statement-body interpretation. */
public final class AccountMapStorage implements AccountMapState {
    private final SourceEdits edits;
    public AccountMapStorage(SourceEdits edits){this.edits=edits;}
    private static String name(Field field){return field.name().replace('_','-');}
    public String get(Field field){return edits.get(name(field));}
    public void put(Field field,String value){edits.put(name(field),value);}
    public void move(Field target,Field source){edits.mapMove(name(target),name(source));}
    public void low(Field field){edits.mapLow(name(field));}
    public boolean same(Field first,Field second){return edits.mapSame(name(first),name(second));}
    public boolean test(Flag flag){return edits.condition(flag.name().replace('_','-'));}
    public void set(Flag flag){edits.setCondition(flag.name().replace('_','-'));}
    public void perform(Rule rule){edits.run(rule.paragraph);}
    public void initializeNewDetails(){edits.initializeMapDetails();}
    public void messagePrefix(String text){edits.mapMessagePrefix(text);}
}
