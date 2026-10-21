package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.util.*;
import tools.jackson.databind.JsonNode;

/** Bounded Java execution of fully parsed source edit statements.
 * Per-interaction scratch storage; never a session, database or reference oracle.
 */
public final class SourceEdits {
    private final JsonNode model;
    private final java.time.Clock clock;
    private final Commarea storage;
    private ScreenFrame screen;
    private final Set<String> stored=new HashSet<>();
    private static final class Transfer extends RuntimeException{
        final String label;Transfer(String label){super(null,null,false,false);this.label=label;}
    }
    private final Map<String,String> values=new LinkedHashMap<>();
    private final List<Location> trace=new ArrayList<>();private int steps;
    public record Location(String source,int line){}
    private record Value(String text,boolean numeric,boolean figurative){}
    public SourceEdits(JsonNode model){this(model,java.time.Clock.systemUTC());}
    public SourceEdits(JsonNode model,java.time.Clock clock){
        this.model=model;this.clock=clock;
        storage=model.path("storage").isObject()?new Commarea(model.path("storage"),null):null;
        if(storage!=null)for(JsonNode field:model.path("storage").path("fields")){
            String path=field.path("path").asText();stored.add(path.substring(path.lastIndexOf('.')+1));}
        if(storage!=null)for(JsonNode literal:model.path("storage_literals"))storage.copyBytes(literal.path("offset").asInt(),Commarea.encode(literal.path("value").asText()));
        for(var entry:model.path("fields").properties())if(!entry.getValue().has("alias_of") && (!stored.contains(entry.getKey()) || entry.getValue().path("explicit_initial").asBoolean()))put(entry.getKey(),entry.getValue().path("initial").asText());
        for(String flag:List.of("INPUT-OK","WS-RETURN-MSG-OFF"))if(model.path("conditions").has(flag))setCondition(flag);
    }
    public void attachScreen(ScreenFrame frame){
        screen=frame;
        for(var entry:model.path("fields").properties())if(entry.getValue().path("screen_part").asText().equals("O"))
            values.put(entry.getKey(),frame.values.get(entry.getValue().path("screen_field").asText()));
    }
    public void receiveScreen(Map<String,String> input){
        if(screen==null)throw new IllegalStateException("screen-not-attached");
        Map<String,String> received=screen.receive(input);
        for(var entry:model.path("fields").properties()){
            JsonNode f=entry.getValue();if(!f.path("screen_part").asText().equals("I"))continue;
            String name=f.path("screen_field").asText();Map<String,Object> a=screen.attributes.get(name);
            // Protected FSET values originate in the server-rendered screen only.
            String value=received.get(name);
            if(value==null)value=Boolean.TRUE.equals(a.get("modified"))?screen.values.get(name):"\u0000".repeat(f.path("length").asInt());
            put(entry.getKey(),value);
        }
    }
    private void screenWrite(JsonNode f,String value){
        if(screen==null||!f.has("screen_field"))return;
        String name=f.path("screen_field").asText(),part=f.path("screen_part").asText();
        if(part.equals("I")&&!f.path("input_overlay_output").asBoolean())return;
        if(part.equals("O")||part.equals("I")){
            // BMS LOW-VALUES leaves the physical field unchanged.
            if(!value.isEmpty()&&value.charAt(0)==0)return;
            String visible=value.replace('\u0000',' ');
            screen.set(name,visible);if(name.equals("ERRMSG"))screen.message=visible.stripTrailing();return;
        }
        if(part.equals("L")){if(value.equals("-1"))screen.cursor=name;return;}
        Map<String,Object> attributes=screen.attributes.get(name);String symbol=value.stripTrailing();
        if(part.equals("C")){
            attributes.put("color",switch(symbol){case "DFHRED"->"RED";case "DFHGREEN"->"GREEN";case "DFHDFCOL"->screen.field(name).path("color").asText();default->throw new IllegalArgumentException("bms-color:"+symbol);});return;
        }
        if(!part.equals("A"))throw new IllegalArgumentException("bms-attribute-kind");
        // CICS DFHBMSCA: PRF includes MDT; FSE sets MDT without protection.
        switch(symbol){
            case "DFHBMPRO":attributes.put("protected",true);attributes.put("modified",false);attributes.put("hidden",false);break;
            case "DFHBMUNP":attributes.put("protected",false);attributes.put("modified",false);attributes.put("hidden",false);break;
            case "DFHBMPRF":attributes.put("protected",true);attributes.put("modified",true);attributes.put("hidden",false);attributes.put("intensity","NORMAL");break;
            case "DFHBMFSE":attributes.put("protected",false);attributes.put("modified",true);attributes.put("hidden",false);attributes.put("intensity","NORMAL");break;
            case "DFHBMASB":attributes.put("protected",true);attributes.put("autoskip",true);attributes.put("modified",false);attributes.put("hidden",false);attributes.put("intensity","BRIGHT");break;
            case "DFHBMDAR":attributes.put("protected",false);attributes.put("modified",false);attributes.put("hidden",true);attributes.put("intensity","DARK");break;
            default:throw new IllegalArgumentException("bms-basic-attribute:"+symbol);
        }
    }
    public void loadArea(Commarea area){
        if(!model.has("area_offset")||area.bytes().length!=model.path("area_length").asInt())throw new IllegalArgumentException("edit-area-layout");
        storage.copyBytes(model.path("area_offset").asInt(),area.bytes());
    }
    public void saveArea(Commarea area){
        int start=model.path("area_offset").asInt(),length=model.path("area_length").asInt();
        if(area.bytes().length!=length)throw new IllegalArgumentException("edit-area-layout");
        area.copyBytes(0,Arrays.copyOfRange(storage.bytes(),start,start+length));
    }
    private JsonNode field(String name){JsonNode f=model.path("fields").path(name);if(f.isMissingNode())throw new IllegalArgumentException("edit-field:"+name);return f;}
    public String get(String name){JsonNode f=field(name);
        if(stored.contains(name))return storage.unsignedDisplayInteger(name)?storage.displayBytes(name):storage.get(name);
        if(f.has("alias_of")){String raw=get(f.path("alias_of").asText());
            if(!raw.matches("[0-9]+"))throw new IllegalArgumentException("edit-numeric-alias");return raw;}
        String value=values.get(name);
        if(f.path("type").asText().equals("number")){
            boolean negative=value.startsWith("-");String absolute=negative?value.substring(1):value;
            int width=f.path("length").asInt()+(f.path("scale").asInt()>0?1:0);
            value=(negative?"-":"")+"0".repeat(Math.max(0,width-absolute.length()))+absolute;
        }return value;
    }
    public void put(String name,String value){JsonNode f=field(name);
        if(stored.contains(name)){
            if(f.path("type").asText().equals("text")){int n=f.path("length").asInt();value=(value+" ".repeat(n)).substring(0,n);}
            storage.set(name,value);return;
        }
        if(f.path("type").asText().equals("number")){
            BigDecimal number=new BigDecimal(value).setScale(f.path("scale").asInt(),java.math.RoundingMode.UNNECESSARY);
            String digits=number.toPlainString();
            if(f.has("alias_of")){int n=f.path("length").asInt();if(number.signum()<0||digits.length()>n)throw new IllegalArgumentException("edit-alias-range");
                put(f.path("alias_of").asText(),"0".repeat(n-digits.length())+digits);return;}
            values.put(name,digits);screenWrite(f,digits);
        }else {int n=f.path("length").asInt();Commarea.encode(value);String padded=(value+" ".repeat(n)).substring(0,n);values.put(name,padded);screenWrite(f,padded);}
    }
    public List<Location> trace(){return List.copyOf(trace);}
    private void visit(JsonNode node){if(++steps>10000)throw new IllegalStateException("edit-step-limit");trace.add(new Location(node.path("source").asText(),node.path("line").asInt()));}
    private static String trimSpaces(String value){int a=0,b=value.length();while(a<b&&value.charAt(a)==' ')a++;while(b>a&&value.charAt(b-1)==' ')b--;return value.substring(a,b);}
    private static String figurative(String token,int length){
        if(token.startsWith("LOW-VALUE"))return "\u0000".repeat(length);
        if(token.startsWith("SPACE"))return " ".repeat(length);
        if(token.startsWith("ZERO"))return "0".repeat(length);
        throw new IllegalArgumentException("edit-figurative");
    }
    private String conditionValue(String token,String name){
        if(token.startsWith("'"))return token.substring(1,token.length()-1).replace("''","'");
        return token.matches("[0-9]+")?token:figurative(token,field(name).path("length").asInt());
    }
    public boolean condition(String name){JsonNode condition=model.path("conditions").path(name);
        if(condition.isMissingNode())throw new IllegalArgumentException("edit-condition:"+name);
        String parent=condition.path("parent").asText();String actual=get(parent);
        boolean numeric=field(parent).path("type").asText().equals("number");
        for(JsonNode v:condition.path("values"))if(compare(actual,conditionValue(v.asText(),parent),numeric)==0)return true;
        for(JsonNode range:condition.path("ranges"))if(compare(actual,conditionValue(range.path("lower").asText(),parent),numeric)>=0
            &&compare(actual,conditionValue(range.path("upper").asText(),parent),numeric)<=0)return true;
        return false;
    }
    public void setCondition(String name){JsonNode c=model.path("conditions").path(name);
        if(c.isMissingNode())throw new IllegalArgumentException("edit-condition:"+name);
        String parent=c.path("parent").asText();
        if(c.path("values").isEmpty())throw new IllegalArgumentException("edit-set-range-condition");
        put(parent,conditionValue(c.path("values").get(0).asText(),parent));
    }
    private static int compare(String a,String b,boolean numeric){
        if(numeric&&a.matches("[+-]?[0-9]+(?:[.][0-9]+)?")&&b.matches("[+-]?[0-9]+(?:[.][0-9]+)?"))
            return new BigDecimal(a).compareTo(new BigDecimal(b));
        // Numeric DISPLAY aliases may contain LOW-VALUES or invalid input.
        // Preserve the disclosed EBCDIC comparison bound until source validation.
        int n=Math.max(a.length(),b.length());return Arrays.compareUnsigned(Commarea.encode(a+" ".repeat(n-a.length())),Commarea.encode(b+" ".repeat(n-b.length())));
    }
    private static boolean paddedEqual(String a,String b){int n=Math.max(a.length(),b.length());return (a+" ".repeat(n-a.length())).equals(b+" ".repeat(n-b.length()));}
    private Value evaluate(JsonNode e){visit(e);String op=e.path("op").asText();
        switch(op){
            case "delimited":{Value v=evaluate(e.path("operand"));String delimiter=e.path("delimiter").asText();int at=v.text().indexOf(delimiter);return new Value(at<0?v.text():v.text().substring(0,at),false,false);}
            case "literal":return new Value(e.path("value").asText(),false,false);
            case "number":return new Value(e.path("value").asText(),true,false);
            case "figurative":return new Value(e.path("value").asText(),false,true);
            case "field":{String n=e.path("name").asText();return new Value(get(n),field(n).path("type").asText().equals("number"),false);}
            case "slice":{String text=evaluate(e.path("operand")).text();int a=integer(e.path("start"))-1,n=e.path("remaining").asBoolean()?text.length()-a:integer(e.path("length"));
                if(a<0||n<1||a+n>text.length())throw new IllegalArgumentException("edit-reference-modification");return new Value(text.substring(a,a+n),false,false);}
            case "UPPER-CASE":return new Value(evaluate(e.path("operand")).text().toUpperCase(Locale.ROOT),false,false);
            case "LOWER-CASE":return new Value(evaluate(e.path("operand")).text().toLowerCase(Locale.ROOT),false,false);
            case "TRIM":return new Value(trimSpaces(evaluate(e.path("operand")).text()),false,false);
            case "LENGTH":return new Value(Integer.toString(evaluate(e.path("operand")).text().length()),true,false);
            case "CURRENT-DATE":return new Value(java.time.ZonedDateTime.now(clock).format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSxx",Locale.ROOT)),false,false);
            case "INTEGER-OF-DATE":{
                String value=evaluate(e.path("operand")).text();
                var date=java.time.LocalDate.parse(value,java.time.format.DateTimeFormatter.BASIC_ISO_DATE);
                return new Value(Long.toString(java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.of(1600,12,31),date)),true,false);}
            case "TEST-NUMVAL-C":return new Value(CobolNumber.valid(evaluate(e.path("operand")).text(),true)?"0":"1",true,false);
            case "TEST-NUMVAL":{
                // This date COPY uses only equality to zero, never the failure position.
                String text=trimSpaces(evaluate(e.path("operand")).text());
                return new Value(text.matches("[+-]?[0-9]+(?:[.][0-9]*)?")?"0":"1",true,false);}

            case "NUMVAL-C":return new Value(CobolNumber.parse(evaluate(e.path("operand")).text(),true).toPlainString(),true,false);
            case "NUMVAL":{String text=trimSpaces(evaluate(e.path("operand")).text());
                if(!text.matches("[+-]?[0-9]+(?:[.][0-9]*)?"))throw new IllegalArgumentException("edit-numval-outside-proved-subset");
                return new Value(new BigDecimal(text).toPlainString(),true,false);}
            default:throw new IllegalArgumentException("edit-expression:"+op);
        }
    }
    private int integer(JsonNode e){return new BigDecimal(evaluate(e).text()).intValueExact();}
    private boolean test(JsonNode e){visit(e);switch(e.path("op").asText()){
        case "or":return test(e.path("left"))||test(e.path("right"));
        case "and":return test(e.path("left"))&&test(e.path("right"));
        case "not":return !test(e.path("operand"));
        case "condition":return condition(e.path("name").asText());
        case "numeric":return evaluate(e.path("operand")).text().matches("[0-9]+");
        case "compare":{
            Value a=evaluate(e.path("left")),b=evaluate(e.path("right"));
            String left=a.figurative()?figurative(a.text(),b.text().length()):a.text();
            String right=b.figurative()?figurative(b.text(),left.length()):b.text();int comparison;
            if(a.numeric()||b.numeric()){
                if(left.matches("[+-]?[0-9]+(?:[.][0-9]+)?")&&right.matches("[+-]?[0-9]+(?:[.][0-9]+)?"))comparison=new BigDecimal(left).compareTo(new BigDecimal(right));
                else {
                    // Explicit deterministic reference assumption for invalid DISPLAY bytes:
                    // retain them until the source's NUMERIC check, compare in EBCDIC order.
                    int n=Math.max(left.length(),right.length());
                    if(left.matches("[0-9]+"))left="0".repeat(n-left.length())+left;
                    if(right.matches("[0-9]+"))right="0".repeat(n-right.length())+right;
                    comparison=Arrays.compareUnsigned(Commarea.encode(left),Commarea.encode(right));
                }
            }
            else{int n=Math.max(left.length(),right.length());comparison=Arrays.compareUnsigned(Commarea.encode(left+" ".repeat(n-left.length())),Commarea.encode(right+" ".repeat(n-right.length())));}
            return switch(e.path("operator").asText()){case "EQUAL","="->comparison==0;case "<>"->comparison!=0;case ">"->comparison>0;case "<"->comparison<0;case ">="->comparison>=0;case "<="->comparison<=0;default->throw new IllegalArgumentException("edit-comparator");};}
        default:throw new IllegalArgumentException("edit-predicate");
    }}
    private void assign(JsonNode target,Value value,boolean string){
        if(target.path("op").asText().equals("field")){
            String name=target.path("name").asText();int n=field(name).path("length").asInt();String text=value.figurative()?figurative(value.text(),n):value.text();
            if(!value.numeric()&&!value.figurative()&&stored.contains(name)&&storage.unsignedDisplayInteger(name)&&!text.matches("[0-9]+")){
                storage.moveDisplayBytes(name,text);return;
            }
            if(string){String previous=get(name);int length=Math.min(text.length(),previous.length());text=text.substring(0,length)+previous.substring(length);}
            if(field(name).path("type").asText().equals("edited") && value.numeric())text=ScreenProjection.edited(text,field(name).path("picture").asText());
            put(name,text);return;
        }
        if(target.path("op").asText().equals("slice")&&target.path("operand").path("op").asText().equals("field")){
            String name=target.path("operand").path("name").asText(),old=get(name);int start=integer(target.path("start"))-1,n=target.path("remaining").asBoolean()?old.length()-start:integer(target.path("length"));
            if(start<0||n<1||start+n>old.length())throw new IllegalArgumentException("edit-reference-modification");
            String text=value.figurative()?figurative(value.text(),n):value.text();text=(text+" ".repeat(n)).substring(0,n);
            put(name,old.substring(0,start)+text+old.substring(start+n));return;
        }throw new IllegalArgumentException("edit-assignment-target");
    }
    private boolean execute(JsonNode statements){return execute(statements,0);}
    private boolean execute(JsonNode statements,int start){for(int i=start;i<statements.size();i++){JsonNode statement=statements.get(i);visit(statement);switch(statement.path("op").asText()){
        case "if":if(execute(statement.path(test(statement.path("test"))?"yes":"no")))return true;break;
        case "evaluate":{
            for(JsonNode branch:statement.path("branches")){
                boolean match=branch.path("default").asBoolean();
                for(JsonNode condition:branch.path("tests"))if(test(condition)){match=true;break;}
                if(match){if(execute(branch.path("actions")))return true;break;}
            }break;}
        case "lookup":{
            String sought=evaluate(statement.path("value")).text();JsonNode found=null;
            for(JsonNode row:model.path("lookups").path(statement.path("table").asText()))if(paddedEqual(row.path("key").asText(),sought)){found=row;break;}
            if(found==null){if(execute(statement.path("missing")))return true;}
            else{put(statement.path("description_field").asText(),found.path("description").asText());if(execute(statement.path("found")))return true;}
            break;}
        case "set":setCondition(statement.path("name").asText());break;
        case "move":{Value value=evaluate(statement.path("value"));for(JsonNode target:statement.path("targets"))assign(target,value,false);break;}
        case "string":{StringBuilder text=new StringBuilder();for(JsonNode piece:statement.path("pieces"))text.append(evaluate(piece).text());assign(statement.path("target"),new Value(text.toString(),false,false),true);break;}
        case "convert":{JsonNode target=statement.path("target");String text=evaluate(target).text(),before=evaluate(statement.path("before")).text(),after=evaluate(statement.path("after")).text();
            if(before.length()!=after.length())throw new IllegalArgumentException("edit-conversion-length");StringBuilder converted=new StringBuilder();
            for(char c:text.toCharArray()){int index=before.indexOf(c);converted.append(index<0?c:after.charAt(index));}
            assign(target,new Value(converted.toString(),false,false),false);break;}

        case "compute":assign(statement.path("target"),evaluate(statement.path("value")),false);break;
        case "divide":{
            BigDecimal[] parts=new BigDecimal(evaluate(statement.path("value")).text()).divideAndRemainder(new BigDecimal(evaluate(statement.path("divisor")).text()));
            assign(statement.path("target"),new Value(parts[0].toPlainString(),true,false),false);
            assign(statement.path("remainder"),new Value(parts[1].toPlainString(),true,false),false);break;}
        case "initialize":{
            for(JsonNode target:statement.path("targets")){
                if(!target.path("op").asText().equals("field"))throw new IllegalArgumentException("edit-initialize-target");
                String name=target.path("name").asText();JsonNode f=field(name);
                if(stored.contains(name))storage.initialize(name);else put(name,f.path("type").asText().equals("number")?"0":"");
            }break;}
        case "date-service":dateService();break;
        case "perform":run(statement.path("paragraph").asText());break;
        case "jump":throw new Transfer(statement.path("label").asText());
        case "label":break;
        case "return":return true;
        case "continue":break;
        default:throw new IllegalArgumentException("edit-statement");
    }}return false;}
    private void dateService(){
        if(!get("WS-DATE-FORMAT").equals("YYYYMMDD"))throw new IllegalArgumentException("date-service-format");
        String date=get("WS-EDIT-DATE-CCYYMMDD"),code="FC-INVALID-DATE";
        try{java.time.LocalDate.parse(date,java.time.format.DateTimeFormatter.BASIC_ISO_DATE);}
        catch(java.time.DateTimeException invalid){code="FC-BAD-DATE-VALUE";}
        JsonNode feedback=model.path("service").path("feedback").path(code);
        if(feedback.isMissingNode())throw new IllegalArgumentException("date-service-feedback-unbound");
        put("WS-SEVERITY-N",Integer.toString(feedback.path("severity").asInt()));
        put("WS-MSG-NO-N",Integer.toString(feedback.path("message").asInt()));
    }
    private void runAccountInputRule(String paragraph) {
        AccountInputRules.Outcome outcome;
        String flag;
        if (paragraph.equals("1215-EDIT-MANDATORY")) {
            String value=get("WS-EDIT-ALPHANUM-ONLY");
            int length=Integer.parseInt(get("WS-EDIT-ALPHANUM-LENGTH"));
            outcome=AccountInputRules.validateRequired(value.substring(0,length));
            flag="WS-EDIT-MANDATORY-FLAGS";
            put(flag,outcome==AccountInputRules.Outcome.VALID?"\u0000":"B");
            trace.add(new Location("app/cbl/COACTUPC.cbl",1824));
        } else if (paragraph.equals("1220-EDIT-YESNO")) {
            outcome=AccountInputRules.validateYesNo(get("WS-EDIT-YES-NO").charAt(0));
            flag="WS-EDIT-YES-NO";
            // A valid Y/N is not overwritten; it is copied into account flags later.
            if(outcome!=AccountInputRules.Outcome.VALID)
                put(flag,outcome==AccountInputRules.Outcome.MISSING?"B":"0");
            trace.add(new Location("app/cbl/COACTUPC.cbl",1856));
        } else throw new IllegalArgumentException("untranslated-native-rule:"+paragraph);
        if(outcome==AccountInputRules.Outcome.VALID)return;
        setCondition("INPUT-ERROR");
        // Quirk: retain the first error, fixed-width label truncation and space-only trim.
        if(condition("WS-RETURN-MSG-OFF")) {
            String suffix=outcome==AccountInputRules.Outcome.MISSING?" must be supplied.":" must be Y or N.";
            put("WS-RETURN-MSG",trimSpaces(get("WS-EDIT-VARIABLE-NAME"))+suffix);
        }
    }
    private void runAccountTextRule(String paragraph) {
        String whole=get("WS-EDIT-ALPHANUM-ONLY");
        int length=Integer.parseInt(get("WS-EDIT-ALPHANUM-LENGTH"));
        String value=whole.substring(0,length);
        var result=switch(paragraph) {
            case "1225-EDIT-ALPHA-REQD" -> AccountTextRules.requiredName(value);
            case "1230-EDIT-ALPHANUM-REQD" -> AccountTextRules.requiredText(value);
            case "1235-EDIT-ALPHA-OPT" -> AccountTextRules.optionalName(value);
            case "1240-EDIT-ALPHANUM-OPT" -> AccountTextRules.optionalText(value);
            case "1245-EDIT-NUM-REQD" -> AccountTextRules.requiredNonzeroDigits(value);
            default -> throw new IllegalArgumentException("untranslated-text-rule:"+paragraph);
        };
        boolean alpha=paragraph.equals("1225-EDIT-ALPHA-REQD") || paragraph.equals("1235-EDIT-ALPHA-OPT");
        String flag=alpha?"WS-EDIT-ALPHA-ONLY-FLAGS":"WS-EDIT-ALPHANUM-ONLY-FLAGS";
        put(flag,switch(result.status()) { case VALID -> "\u0000"; case MISSING -> "B"; default -> "0"; });
        if(result.converted()) {
            String table=alpha?"LIT-ALL-ALPHA-FROM":"LIT-ALL-ALPHANUM-FROM";
            put(table,get(table+"-X"));
            // INSPECT mutates only the declared prefix, including on invalid input.
            put("WS-EDIT-ALPHANUM-ONLY",result.scratch()+whole.substring(length));
        }
        int line=switch(paragraph) { case "1225-EDIT-ALPHA-REQD" -> 1898; case "1230-EDIT-ALPHANUM-REQD" -> 1955;
            case "1235-EDIT-ALPHA-OPT" -> 2012; case "1240-EDIT-ALPHANUM-OPT" -> 2061; default -> 2109; };
        trace.add(new Location("app/cbl/COACTUPC.cbl",line));
        if(result.status()==AccountTextRules.Status.VALID)return;
        String suffix=switch(result.status()) {
            case MISSING -> " must be supplied.";
            case ZERO -> " must not be zero.";
            default -> paragraph.equals("1245-EDIT-NUM-REQD")?" must be all numeric.":
                alpha?" can have alphabets only.":" can have numbers or alphabets only.";
        };
        nativeInputError(suffix);
    }
    private void runAccountMoneyRule() {
        var result=AccountMoneyRule.validate(get("WS-EDIT-SIGNED-NUMBER-9V2-X"));
        put("WS-FLG-SIGNED-NUMBER-EDIT",switch(result.outcome()) { case VALID -> "\u0000"; case MISSING -> "B"; default -> "0"; });
        trace.add(new Location("app/cbl/COACTUPC.cbl",2180));
        if(result.outcome()!=AccountInputRules.Outcome.VALID)
            nativeInputError(result.outcome()==AccountInputRules.Outcome.MISSING?" must be supplied.":" is not valid");
    }
    private void runAccountSsnRule() {
        var result=AccountSsnRule.validate(get("ACUP-NEW-CUST-SSN-1"),get("ACUP-NEW-CUST-SSN-2"),get("ACUP-NEW-CUST-SSN-3"));
        trace.add(new Location("app/cbl/COACTUPC.cbl",2431));
        applySsnPart(1,"SSN: First 3 chars",result.first());
        if(result.first().status()==AccountTextRules.Status.VALID) {
            put("WS-EDIT-US-SSN-PART1",result.first().input());
            if(result.restrictedFirst()) {
                put("WS-EDIT-US-SSN-PART1-FLGS","0");
                nativeInputError(": should not be 000, 666, or between 900 and 999");
            }
        }
        String[] labels={"SSN 4th & 5th chars","SSN Last 4 chars"};
        for(int i=0;i<result.remaining().size();i++)applySsnPart(i+2,labels[i],result.remaining().get(i));
    }
    private void applySsnPart(int number,String label,AccountSsnRule.Part part) {
        put("WS-EDIT-VARIABLE-NAME",label);
        put("WS-EDIT-ALPHANUM-ONLY",part.input());
        put("WS-EDIT-ALPHANUM-LENGTH",Integer.toString(part.input().length()));
        String flag=switch(part.status()) { case VALID -> "\u0000"; case MISSING -> "B"; default -> "0"; };
        put("WS-EDIT-ALPHANUM-ONLY-FLAGS",flag);
        put("WS-EDIT-US-SSN-PART"+number+"-FLGS",flag);
        if(part.status()!=AccountTextRules.Status.VALID)nativeInputError(switch(part.status()) {
            case MISSING -> " must be supplied."; case ZERO -> " must not be zero."; default -> " must be all numeric.";
        });
    }
    private void runAccountFicoRule() {
        trace.add(new Location("app/cbl/COACTUPC.cbl",2514));
        // A successful range edit leaves the existing flag untouched.
        if(!AccountFicoRule.validDisplay(get("ACUP-NEW-CUST-FICO-SCORE"))) {
            setCondition("FLG-FICO-SCORE-NOT-OK");
            nativeInputError(": should be between 300 and 850");
        }
    }
    private Set<String> sourceLookupValues(String condition) {
        JsonNode data=model.path("conditions").path(condition);
        if(!data.isObject() || !data.path("values").isArray() || !data.path("ranges").isArray())
            throw new IllegalArgumentException("location-condition-shape");
        if(!data.path("ranges").isEmpty())throw new IllegalArgumentException("location-range-condition");
        Set<String> literals=new HashSet<>();
        for(JsonNode item:data.path("values")) {
            String quoted=item.asText();
            if(!item.isTextual() || quoted.length()<2 || !quoted.startsWith("'") || !quoted.endsWith("'"))
                throw new IllegalArgumentException("location-literal-condition");
            literals.add(quoted.substring(1,quoted.length()-1).replace("''","'"));
        }
        if(literals.isEmpty())throw new IllegalArgumentException("location-empty-condition");
        return Set.copyOf(literals);
    }
    private void runAccountLocationRule(String paragraph) {
        String state=get("ACUP-NEW-CUST-ADDR-STATE-CD");
        if(paragraph.equals("1270-EDIT-US-STATE-CD")) {
            var result=AccountLocationRules.state(state,sourceLookupValues("VALID-US-STATE-CODE"));
            put("US-STATE-CODE-TO-EDIT",result.scratch());
            trace.add(new Location("app/cbl/COACTUPC.cbl",2494));
            if(!result.valid()) {
                setCondition("FLG-STATE-NOT-OK");
                nativeInputError(": is not a valid state code");
            }
        } else if(paragraph.equals("1280-EDIT-US-STATE-ZIP-CD")) {
            var result=AccountLocationRules.stateZip(state,get("ACUP-NEW-CUST-ADDR-ZIP"),
                sourceLookupValues("VALID-US-STATE-ZIP-CD2-COMBO"));
            put("US-STATE-AND-FIRST-ZIP2",result.scratch());
            trace.add(new Location("app/cbl/COACTUPC.cbl",2537));
            if(!result.valid()) {
                setCondition("INPUT-ERROR");
                setCondition("FLG-STATE-NOT-OK");
                setCondition("FLG-ZIPCODE-NOT-OK");
                // This source message has no variable-name prefix; keep the first error.
                if(condition("WS-RETURN-MSG-OFF"))put("WS-RETURN-MSG","Invalid zip code for state");
            }
        } else throw new IllegalArgumentException("untranslated-location-rule:"+paragraph);
    }
    private void nativeInputError(String suffix) {
        setCondition("INPUT-ERROR");
        if(condition("WS-RETURN-MSG-OFF"))put("WS-RETURN-MSG",trimSpaces(get("WS-EDIT-VARIABLE-NAME"))+suffix);
    }
    public void run(String paragraph){
        if(model.path("native_paragraphs").has(paragraph)) {
            switch(model.path("native_paragraphs").path(paragraph).asText()) {
                case "AccountInputRules" -> runAccountInputRule(paragraph);
                case "AccountTextRules" -> runAccountTextRule(paragraph);
                case "AccountMoneyRule" -> runAccountMoneyRule();
                case "AccountSsnRule" -> runAccountSsnRule();
                case "AccountFicoRule" -> runAccountFicoRule();
                case "AccountLocationRules" -> runAccountLocationRule(paragraph);
                default -> throw new IllegalArgumentException("untranslated-native-class");
            }
            return;
        }
        JsonNode statements=model.path("paragraphs").path(paragraph);
        if(statements.isMissingNode())throw new IllegalArgumentException("untranslated-edit-paragraph:"+paragraph);
        Map<String,Integer> labels=new HashMap<>();for(int i=0;i<statements.size();i++){
            JsonNode s=statements.get(i);if(s.path("op").asText().equals("label")&&labels.put(s.path("name").asText(),i)!=null)throw new IllegalArgumentException("duplicate-edit-label");}
        int start=0;
        while(true){try{execute(statements,start);return;}catch(Transfer transfer){
            Integer target=labels.get(transfer.label);if(target==null)throw new IllegalArgumentException("edit-transfer-outside-paragraph");start=target;
        }}
    }
}
