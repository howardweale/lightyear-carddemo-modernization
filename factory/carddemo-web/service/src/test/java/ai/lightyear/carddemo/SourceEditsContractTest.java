package ai.lightyear.carddemo;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Small language-contract tests supplement, and never supply expectations to,
 * the independent raw COBOL scenario replay. Literal expectations are hand specified. */
class SourceEditsContractTest {
    final JsonMapper json=JsonMapper.builder().build();
    Map<String,Object> field(String name){return Map.of("op","field","name",name);}
    Map<String,Object> literal(String value){return Map.of("op","literal","value",value);}
    Map<String,Object> number(int value){return Map.of("op","number","value",Integer.toString(value));}
    Map<String,Object> move(Object value,Object target){return Map.of("op","move","value",value,"targets",List.of(target),"source","contract","line",1);}
    Map<String,Object> slice(int start,int length){return Map.of("op","slice","operand",field("T"),"start",number(start),"length",number(length));}
    Map<String,Object> remaining(int start){return Map.of("op","slice","operand",field("T"),"start",number(start),"remaining",true);}
    SourceEdits edits(List<?> statements){
        return new SourceEdits(json.valueToTree(Map.of("fields",Map.of(
            "T",Map.of("type","text","length",6,"initial","ABCDEF"),
            "R",Map.of("type","text","length",6,"initial","------"),
            "N",Map.of("type","number","length",3,"initial","0"),
            "F",Map.of("type","text","length",1,"initial","N")),
            "lookups",Map.of("L",List.of(Map.of("key","A","description","FOUND"))),
            "paragraphs",Map.of("P",statements))));
    }
    @Test void referenceModificationIncludesItsLastCellAndRejectsEveryOutOfRangeEdge(){
        for(Object expression:List.of(slice(1,6),remaining(1))){var e=edits(List.of(move(expression,field("R"))));e.run("P");assertEquals("ABCDEF",e.get("R"));}
        var last=edits(List.of(move(slice(6,1),field("R"))));last.run("P");assertEquals("F     ",last.get("R"));
        var write=edits(List.of(move(literal("xy"),slice(2,3))));write.run("P");assertEquals("Axy EF",write.get("T"));
        var tail=edits(List.of(move(literal("Z"),remaining(4))));tail.run("P");assertEquals("ABCZ  ",tail.get("T"));
        for(int[] pair:new int[][]{{0,1},{1,0},{6,2},{7,1}}){
            var read=edits(List.of(move(slice(pair[0],pair[1]),field("R"))));assertThrows(IllegalArgumentException.class,()->read.run("P"));
            var badWrite=edits(List.of(move(literal("X"),slice(pair[0],pair[1]))));assertThrows(IllegalArgumentException.class,()->badWrite.run("P"));
        }
    }
    @Test void allComparisonOperatorsIncludeEqualityAndNumericRatherThanLexicalOrdering(){
        for(String operator:List.of("=","EQUAL","<>",">","<",">=","<="))for(int n:new int[]{1,2,10}){
            boolean wanted=switch(operator){case "=","EQUAL"->n==2;case "<>"->n!=2;case ">"->n>2;case "<"->n<2;case ">="->n>=2;default->n<=2;};
            Object test=Map.of("op","compare","left",field("N"),"right",number(2),"operator",operator);
            Object yes=move(literal("Y"),field("F"));
            Object no=move(literal("N"),field("F"));
            var e=edits(List.of(Map.of("op","if","test",test,"yes",List.of(yes),"no",List.of(no))));
            e.put("N",Integer.toString(n));e.run("P");assertEquals(wanted?"Y":"N",e.get("F"),operator+" "+n);
        }
        // Fixed text pads with spaces; numeric DISPLAY invalid-byte comparisons
        // retain the disclosed EBCDIC bound and zero-pad only the numeric operand.
        for(Object[] c:List.of(new Object[]{literal("A"),literal("A  "),"=",true},new Object[]{literal("12X"),number(1),">",true},new Object[]{number(1),literal("12X"),"<",true})){
            var e=edits(List.of(Map.of("op","if","test",Map.of("op","compare","left",c[0],"right",c[1],"operator",c[2]),"yes",List.of(move(literal("Y"),field("F"))),"no",List.of())));
            e.run("P");assertEquals("Y",e.get("F"));
        }
    }
    @Test void returnsPropagateThroughConditionalEvaluateAndBothLookupBranches(){
        var stop=List.of(move(literal("FIRST"),field("R")),Map.of("op","return"),move(literal("BAD"),field("R")));
        List<Object> controls=new ArrayList<>();
        controls.add(Map.of("op","if","test",Map.of("op","compare","left",number(1),"right",number(1),"operator","="),"yes",stop,"no",List.of()));
        controls.add(Map.of("op","evaluate","branches",List.of(Map.of("default",true,"tests",List.of(),"actions",stop))));
        for(String value:List.of("A","Z"))controls.add(Map.of("op","lookup","value",literal(value),"table","L","description_field","T","found",stop,"missing",stop));
        for(Object control:controls){var e=edits(List.of(control,move(literal("LATE"),field("R"))));e.run("P");assertEquals("FIRST ",e.get("R"));}
    }
    @Test void divisionStringInitializationAndTrimmingPreserveTheirReceivingStorage(){
        var e=edits(List.of(Map.of("op","divide","value",number(17),"divisor",number(5),"target",field("N"),"remainder",field("R"))));
        e.run("P");assertEquals("003",e.get("N"));assertEquals("2     ",e.get("R"));
        var string=edits(List.of(Map.of("op","string","pieces",List.of(literal("xy")),"target",field("T"))));string.run("P");assertEquals("xyCDEF",string.get("T"));
        var init=edits(List.of(Map.of("op","initialize","targets",List.of(field("T"),field("N")))));init.put("N","123");init.run("P");assertEquals("      ",init.get("T"));assertEquals("000",init.get("N"));
        for(String text:List.of("", "   ", "  A  ", "\u0000 A \u0000")){
            var trim=edits(List.of(move(Map.of("op","TRIM","operand",literal(text)),field("R"))));trim.run("P");
            assertEquals(ScreenFrame.pad(text.equals("\u0000 A \u0000")?text:text.strip(),6),trim.get("R"));
        }
    }
    @Test void storedUnsignedDisplayMovesRetainInvalidBytesAndInitializeRestoresZero(){
        var model=Map.of("storage",Map.of("record_length",3,"fields",List.of(Map.of("path","G.U","offset",0,"length",3,"digits",3,"usage","DISPLAY"))),
            "fields",Map.of("U",Map.of("type","number","length",3)),"paragraphs",Map.of(
                "MOVE",List.of(move(literal("ABC"),field("U"))),"INIT",List.of(Map.of("op","initialize","targets",List.of(field("U"))))));
        var e=new SourceEdits(json.valueToTree(model));e.run("MOVE");assertEquals("ABC",e.get("U"));e.run("INIT");assertEquals("000",e.get("U"));
    }
    @Test void traceIncludesStatementsAndOperandsAndBoundedExecutionRejectsTheNextStep(){
        var e=edits(List.of(move(literal("X"),field("T"))));e.run("P");
        assertEquals(2,e.trace().size());assertEquals(new SourceEdits.Location("contract",1),e.trace().get(0));
        var exact=edits(Collections.nCopies(10000,Map.of("op","continue")));exact.run("P");assertEquals(10000,exact.trace().size());
        var over=edits(Collections.nCopies(10001,Map.of("op","continue")));assertEquals("edit-step-limit",assertThrows(IllegalStateException.class,()->over.run("P")).getMessage());
    }
    @Test void editedPicturesTruncateHighDigitsAndFractionWithoutRounding(){
        assertEquals(" 12.34",ScreenProjection.edited("112.349","-Z9.99"));
        assertEquals(" 99.99",ScreenProjection.edited("99.999","-Z9.99"));
        assertEquals("- 0.00",ScreenProjection.edited("-0.009","-Z9.99"));
        assertEquals("+ 0.00",ScreenProjection.edited("0","+Z9.99"));
        assertEquals("+12.30",ScreenProjection.edited("12.3","+Z9.99"));
        JsonNode last=json.valueToTree(Map.of("operation","field","name","T","offset",5,"length",1));
        assertEquals("F",ChangeDetection.evaluate(last,n->"ABCDEF"));
        for(int[] x:new int[][]{{-1,1},{0,0},{5,2}}){var invalid=json.valueToTree(Map.of("operation","field","name","T","offset",x[0],"length",x[1]));assertThrows(IllegalArgumentException.class,()->ChangeDetection.evaluate(invalid,n->"ABCDEF"));}
    }
}
