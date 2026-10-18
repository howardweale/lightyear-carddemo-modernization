package ai.lightyear.carddemo;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CobolNumberTest {
    @Test void numericAndMonetaryFormsPreserveSignAndFraction(){
        for(String value:new String[]{" - $1,234.56 ","$1,234.56CR","$ 1,234.56 DB","1,234.56-"})
            assertEquals(0,new BigDecimal("-1234.56").compareTo(CobolNumber.parse(value,true)),value);
        for(String value:new String[]{".25"," + $ .25 ","$.25+"})
            assertEquals(0,new BigDecimal("0.25").compareTo(CobolNumber.parse(value,true)),value);
        assertEquals(0,new BigDecimal("1234").compareTo(CobolNumber.parse("1,2,34",true)));
    }
    @Test void malformedAmountsAreNotSilentlyStrippedOrRounded(){
        for(String value:new String[]{""," ","$","12 34","1,,234","1,","1.2,3","$-1","-1-","1cr","1e2","1\t","1.2.3","$$1"})
            assertFalse(CobolNumber.valid(value,true),value);
        assertFalse(CobolNumber.valid("$1",false));
        assertEquals(0,new BigDecimal("12.345").compareTo(CobolNumber.parse("12.345",true)));
    }
}
