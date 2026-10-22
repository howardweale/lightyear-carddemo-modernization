package ai.lightyear.carddemo;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

/** Explicit Java control flow for the two complete date PERFORM ranges.
 * AccountEditState supplies typed storage/88-level data and the existing declared LE adapter;
 * no statement nodes are inspected or executed by these rules.
 */
public final class AccountDateRules {
    private static boolean absent(String value) {
        return value.equals(" ".repeat(value.length())) || value.equals("\0".repeat(value.length()));
    }
    private static String trim(String value) { return value.replaceAll("^ +| +$",""); }
    private static boolean numval(String value) { return trim(value).matches("[+-]?[0-9]+(?:[.][0-9]*)?"); }
    private static void error(AccountEditState state,String suffix,AccountEditState.Flag... flags) {
        state.set(AccountEditState.Flag.INPUT_ERROR);
        for(AccountEditState.Flag flag:flags)state.set(flag);
        if(state.test(AccountEditState.Flag.WS_RETURN_MSG_OFF))state.put(AccountEditState.Field.WS_RETURN_MSG,trim(state.get(AccountEditState.Field.WS_EDIT_VARIABLE_NAME))+suffix);
    }
    private static void year(AccountEditState state) {
        state.set(AccountEditState.Flag.FLG_YEAR_NOT_OK);String year=state.get(AccountEditState.Field.WS_EDIT_DATE_CCYY);
        if(absent(year))error(state," : Year must be supplied.",AccountEditState.Flag.FLG_YEAR_BLANK);
        else if(!year.matches("[0-9]+"))error(state," must be 4 digit number.",AccountEditState.Flag.FLG_YEAR_NOT_OK);
        else if(!state.test(AccountEditState.Flag.THIS_CENTURY) && !state.test(AccountEditState.Flag.LAST_CENTURY))error(state," : Century is not valid.",AccountEditState.Flag.FLG_YEAR_NOT_OK);
        else state.set(AccountEditState.Flag.FLG_YEAR_ISVALID);
    }
    private static void month(AccountEditState state) {
        state.set(AccountEditState.Flag.FLG_MONTH_NOT_OK);String month=state.get(AccountEditState.Field.WS_EDIT_DATE_MM);
        if(absent(month))error(state," : Month must be supplied.",AccountEditState.Flag.FLG_MONTH_BLANK);
        else if(!state.test(AccountEditState.Flag.WS_VALID_MONTH) || !numval(month))
            error(state,": Month must be a number between 1 and 12.",AccountEditState.Flag.FLG_MONTH_NOT_OK);
        else {
            state.put(AccountEditState.Field.WS_EDIT_DATE_MM_N,new BigDecimal(trim(month)).toPlainString());
            state.set(AccountEditState.Flag.FLG_MONTH_ISVALID);
        }
    }
    private static void day(AccountEditState state) {
        state.set(AccountEditState.Flag.FLG_DAY_ISVALID);String day=state.get(AccountEditState.Field.WS_EDIT_DATE_DD);
        if(absent(day)) {error(state," : Day must be supplied.",AccountEditState.Flag.FLG_DAY_BLANK);return;}
        if(!numval(day)) {error(state,":day must be a number between 1 and 31.",AccountEditState.Flag.FLG_DAY_NOT_OK);return;}
        state.put(AccountEditState.Field.WS_EDIT_DATE_DD_N,new BigDecimal(trim(day)).toPlainString());
        if(!state.test(AccountEditState.Flag.WS_VALID_DAY)) {error(state,":day must be a number between 1 and 31.",AccountEditState.Flag.FLG_DAY_NOT_OK);return;}
        state.set(AccountEditState.Flag.FLG_DAY_ISVALID);
    }
    @CobolSource(program="COACTUPC", paragraph="EDIT-DATE-CCYYMMDD", lines="18-331")
    public static void validate(AccountEditState state) {
        state.set(AccountEditState.Flag.WS_EDIT_DATE_IS_INVALID);
        // Component EXIT labels fall through to the following component.
        year(state);month(state);day(state);
        if(!state.test(AccountEditState.Flag.WS_31_DAY_MONTH) && state.test(AccountEditState.Flag.WS_DAY_31)) {
            error(state,":Cannot have 31 days in this month.",AccountEditState.Flag.FLG_DAY_NOT_OK,AccountEditState.Flag.FLG_MONTH_NOT_OK);return;
        }
        if(state.test(AccountEditState.Flag.WS_FEBRUARY) && state.test(AccountEditState.Flag.WS_DAY_30)) {
            error(state,":Cannot have 30 days in this month.",AccountEditState.Flag.FLG_DAY_NOT_OK,AccountEditState.Flag.FLG_MONTH_NOT_OK);return;
        }
        if(state.test(AccountEditState.Flag.WS_FEBRUARY) && state.test(AccountEditState.Flag.WS_DAY_29)) {
            String yearSuffix=state.get(AccountEditState.Field.WS_EDIT_DATE_YY_N);
            // Invalid DISPLAY bytes compare unequal to zero before DIVIDE rejects the year.
            boolean zeroSuffix=yearSuffix.matches("[+-]?[0-9]+(?:[.][0-9]+)?")
                && new BigDecimal(yearSuffix).signum()==0;
            int divisor=zeroSuffix?400:4;
            state.put(AccountEditState.Field.WS_DIV_BY,Integer.toString(divisor));
            BigDecimal[] parts=new BigDecimal(state.get(AccountEditState.Field.WS_EDIT_DATE_CCYY_N)).divideAndRemainder(BigDecimal.valueOf(divisor));
            state.put(AccountEditState.Field.WS_DIVIDEND,parts[0].toPlainString());state.put(AccountEditState.Field.WS_REMAINDER,parts[1].toPlainString());
            if(parts[1].signum()!=0) {
                error(state,":Not a leap year.Cannot have 29 days in this month.",AccountEditState.Flag.FLG_DAY_NOT_OK,AccountEditState.Flag.FLG_MONTH_NOT_OK,AccountEditState.Flag.FLG_YEAR_NOT_OK);return;
            }
        }
        if(!state.test(AccountEditState.Flag.WS_EDIT_DATE_IS_VALID))return;
        state.initializeDateResult();state.put(AccountEditState.Field.WS_DATE_FORMAT,"YYYYMMDD");state.checkDateService();
        if(new BigDecimal(state.get(AccountEditState.Field.WS_SEVERITY_N)).signum()!=0)
            error(state," validation error Sev code: "+state.get(AccountEditState.Field.WS_SEVERITY)+" Message code: "+state.get(AccountEditState.Field.WS_MSG_NO),
                AccountEditState.Flag.FLG_DAY_NOT_OK,AccountEditState.Flag.FLG_MONTH_NOT_OK,AccountEditState.Flag.FLG_YEAR_NOT_OK);
        else if(!state.test(AccountEditState.Flag.INPUT_ERROR))state.set(AccountEditState.Flag.FLG_DAY_ISVALID);
        // EDIT-DATE-LE-EXIT falls through even after a nonzero service result.
        state.set(AccountEditState.Flag.WS_EDIT_DATE_IS_VALID);
    }
    @CobolSource(program="COACTUPC", paragraph="EDIT-DATE-OF-BIRTH", lines="341-372")
    public static void birth(AccountEditState state,Clock clock) {
        LocalDate today=LocalDate.now(clock);
        state.put(AccountEditState.Field.WS_CURRENT_DATE_YYYYMMDD,today.format(DateTimeFormatter.BASIC_ISO_DATE));
        LocalDate birth=LocalDate.parse(state.get(AccountEditState.Field.WS_EDIT_DATE_CCYYMMDD_N),DateTimeFormatter.BASIC_ISO_DATE);
        LocalDate epoch=LocalDate.of(1600,12,31);
        long birthDay=ChronoUnit.DAYS.between(epoch,birth),currentDay=ChronoUnit.DAYS.between(epoch,today);
        state.put(AccountEditState.Field.WS_EDIT_DATE_BINARY,Long.toString(birthDay));state.put(AccountEditState.Field.WS_CURRENT_DATE_BINARY,Long.toString(currentDay));
        if(currentDay<=birthDay)error(state,":cannot be in the future ",AccountEditState.Flag.FLG_DAY_NOT_OK,AccountEditState.Flag.FLG_MONTH_NOT_OK,AccountEditState.Flag.FLG_YEAR_NOT_OK);
    }
}
