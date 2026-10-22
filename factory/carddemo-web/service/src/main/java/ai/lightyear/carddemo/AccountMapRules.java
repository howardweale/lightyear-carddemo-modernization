package ai.lightyear.carddemo;

import java.util.Locale;
import static ai.lightyear.carddemo.AccountMapState.Field.*;
import static ai.lightyear.carddemo.AccountMapState.Flag.*;
import static ai.lightyear.carddemo.AccountMapState.Rule.*;

/** Bounded receive, change detection and ordered validation for COACTUPC. */
public final class AccountMapRules {
    private AccountMapRules() {}
    private static boolean all(String text,char value) {
        return text.chars().allMatch(c -> c==value);
    }
    private static String trimSpaces(String text) {
        int first=0,last=text.length();
        while(first<last && text.charAt(first)==' ')first++;
        while(last>first && text.charAt(last-1)==' ')last--;
        return text.substring(first,last);
    }
    private static void receiveField(AccountMapState s,AccountMapState.Field input,AccountMapState.Field target) {
        String raw=s.get(input);
        if(raw.equals("*"+" ".repeat(raw.length()-1)) || all(raw,' '))s.low(target);
        else s.move(target,input);
    }
    private static void receiveMoney(AccountMapState s,AccountMapState.Field input,
            AccountMapState.Field text,AccountMapState.Field numeric) {
        receiveField(s,input,text);
        // LOW-VALUES are invalid for NUMVAL-C and leave the raw overlay untouched.
        if(CobolNumber.valid(s.get(text),true))
            s.put(numeric,CobolNumber.parse(s.get(input),true).toPlainString());
    }
    @CobolSource(program="COACTUPC", paragraph="1100-RECEIVE-MAP", lines="1039-1428")
    public static void receive(AccountMapState s) {
        s.initializeNewDetails();
        receiveField(s,ACCTSIDI,CC_ACCT_ID);
        s.move(ACUP_NEW_ACCT_ID_X,CC_ACCT_ID);
        if(s.test(ACUP_DETAILS_NOT_FETCHED))return;
        receiveField(s,ACSTTUSI,ACUP_NEW_ACTIVE_STATUS);
        receiveMoney(s,ACRDLIMI,ACUP_NEW_CREDIT_LIMIT_X,ACUP_NEW_CREDIT_LIMIT_N);
        receiveMoney(s,ACSHLIMI,ACUP_NEW_CASH_CREDIT_LIMIT_X,ACUP_NEW_CASH_CREDIT_LIMIT_N);
        receiveMoney(s,ACURBALI,ACUP_NEW_CURR_BAL_X,ACUP_NEW_CURR_BAL_N);
        receiveMoney(s,ACRCYCRI,ACUP_NEW_CURR_CYC_CREDIT_X,ACUP_NEW_CURR_CYC_CREDIT_N);
        receiveMoney(s,ACRCYDBI,ACUP_NEW_CURR_CYC_DEBIT_X,ACUP_NEW_CURR_CYC_DEBIT_N);
        receiveField(s,OPNYEARI,ACUP_NEW_OPEN_YEAR);
        receiveField(s,OPNMONI,ACUP_NEW_OPEN_MON);
        receiveField(s,OPNDAYI,ACUP_NEW_OPEN_DAY);
        receiveField(s,EXPYEARI,ACUP_NEW_EXP_YEAR);
        receiveField(s,EXPMONI,ACUP_NEW_EXP_MON);
        receiveField(s,EXPDAYI,ACUP_NEW_EXP_DAY);
        receiveField(s,RISYEARI,ACUP_NEW_REISSUE_YEAR);
        receiveField(s,RISMONI,ACUP_NEW_REISSUE_MON);
        receiveField(s,RISDAYI,ACUP_NEW_REISSUE_DAY);
        receiveField(s,AADDGRPI,ACUP_NEW_GROUP_ID);
        receiveField(s,ACSTNUMI,ACUP_NEW_CUST_ID_X);
        receiveField(s,ACTSSN1I,ACUP_NEW_CUST_SSN_1);
        receiveField(s,ACTSSN2I,ACUP_NEW_CUST_SSN_2);
        receiveField(s,ACTSSN3I,ACUP_NEW_CUST_SSN_3);
        receiveField(s,DOBYEARI,ACUP_NEW_CUST_DOB_YEAR);
        receiveField(s,DOBMONI,ACUP_NEW_CUST_DOB_MON);
        receiveField(s,DOBDAYI,ACUP_NEW_CUST_DOB_DAY);
        receiveField(s,ACSTFCOI,ACUP_NEW_CUST_FICO_SCORE_X);
        receiveField(s,ACSFNAMI,ACUP_NEW_CUST_FIRST_NAME);
        receiveField(s,ACSMNAMI,ACUP_NEW_CUST_MIDDLE_NAME);
        receiveField(s,ACSLNAMI,ACUP_NEW_CUST_LAST_NAME);
        receiveField(s,ACSADL1I,ACUP_NEW_CUST_ADDR_LINE_1);
        receiveField(s,ACSADL2I,ACUP_NEW_CUST_ADDR_LINE_2);
        receiveField(s,ACSCITYI,ACUP_NEW_CUST_ADDR_LINE_3);
        receiveField(s,ACSSTTEI,ACUP_NEW_CUST_ADDR_STATE_CD);
        receiveField(s,ACSCTRYI,ACUP_NEW_CUST_ADDR_COUNTRY_CD);
        receiveField(s,ACSZIPCI,ACUP_NEW_CUST_ADDR_ZIP);
        receiveField(s,ACSPH1AI,ACUP_NEW_CUST_PHONE_NUM_1A);
        receiveField(s,ACSPH1BI,ACUP_NEW_CUST_PHONE_NUM_1B);
        receiveField(s,ACSPH1CI,ACUP_NEW_CUST_PHONE_NUM_1C);
        receiveField(s,ACSPH2AI,ACUP_NEW_CUST_PHONE_NUM_2A);
        receiveField(s,ACSPH2BI,ACUP_NEW_CUST_PHONE_NUM_2B);
        receiveField(s,ACSPH2CI,ACUP_NEW_CUST_PHONE_NUM_2C);
        receiveField(s,ACSGOVTI,ACUP_NEW_CUST_GOVT_ISSUED_ID);
        receiveField(s,ACSEFTCI,ACUP_NEW_CUST_EFT_ACCOUNT_ID);
        receiveField(s,ACSPFLGI,ACUP_NEW_CUST_PRI_HOLDER_IND);
    }
    @CobolSource(program="COACTUPC", paragraph="1210-EDIT-ACCOUNT", lines="1783-1822")
    public static void account(AccountMapState s) {
        s.set(FLG_ACCTFILTER_NOT_OK);
        String key=s.get(CC_ACCT_ID);
        if(all(key,(char)0) || all(key,' ')) {
            s.set(INPUT_ERROR);s.set(FLG_ACCTFILTER_BLANK);
            if(s.test(WS_RETURN_MSG_OFF))s.set(WS_PROMPT_FOR_ACCT);
            s.put(CDEMO_ACCT_ID,"0");s.put(ACUP_NEW_ACCT_ID,"0");return;
        }
        s.move(ACUP_NEW_ACCT_ID,CC_ACCT_ID);
        if(!key.matches("[0-9]+") || all(key,'0')) {
            s.set(INPUT_ERROR);
            if(s.test(WS_RETURN_MSG_OFF))s.messagePrefix(
                "Account Number if supplied must be a 11 digit Non-Zero Number");
            s.put(CDEMO_ACCT_ID,"0");return;
        }
        s.move(CDEMO_ACCT_ID,CC_ACCT_ID);s.set(FLG_ACCTFILTER_ISVALID);
    }
    private static boolean foldedSame(AccountMapState s,AccountMapState.Field newer,AccountMapState.Field older) {
        return trimSpaces(s.get(newer)).toUpperCase(Locale.ROOT).equals(
            trimSpaces(s.get(older)).toUpperCase(Locale.ROOT));
    }
    @CobolSource(program="COACTUPC", paragraph="1205-COMPARE-OLD-NEW", lines="1681-1779")
    public static void compare(AccountMapState s) {
        s.set(NO_CHANGES_FOUND);
        if(!s.same(ACUP_NEW_ACCT_ID_X,ACUP_OLD_ACCT_ID_X)
                || !s.get(ACUP_NEW_ACTIVE_STATUS).toUpperCase(Locale.ROOT).equals(s.get(ACUP_OLD_ACTIVE_STATUS).toUpperCase(Locale.ROOT))
                || !s.same(ACUP_NEW_CURR_BAL,ACUP_OLD_CURR_BAL)
                || !s.same(ACUP_NEW_CREDIT_LIMIT,ACUP_OLD_CREDIT_LIMIT)
                || !s.same(ACUP_NEW_CASH_CREDIT_LIMIT,ACUP_OLD_CASH_CREDIT_LIMIT)
                || !s.same(ACUP_NEW_OPEN_DATE,ACUP_OLD_OPEN_DATE)
                || !s.same(ACUP_NEW_EXPIRAION_DATE,ACUP_OLD_EXPIRAION_DATE)
                || !s.same(ACUP_NEW_REISSUE_DATE,ACUP_OLD_REISSUE_DATE)
                || !s.same(ACUP_NEW_CURR_CYC_CREDIT,ACUP_OLD_CURR_CYC_CREDIT)
                || !s.same(ACUP_NEW_CURR_CYC_DEBIT,ACUP_OLD_CURR_CYC_DEBIT)
                || !foldedSame(s,ACUP_NEW_GROUP_ID,ACUP_OLD_GROUP_ID)
                || !foldedSame(s,ACUP_NEW_CUST_ID_X,ACUP_OLD_CUST_ID_X)
                || !foldedSame(s,ACUP_NEW_CUST_FIRST_NAME,ACUP_OLD_CUST_FIRST_NAME)
                || !foldedSame(s,ACUP_NEW_CUST_MIDDLE_NAME,ACUP_OLD_CUST_MIDDLE_NAME)
                || !foldedSame(s,ACUP_NEW_CUST_LAST_NAME,ACUP_OLD_CUST_LAST_NAME)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_LINE_1,ACUP_OLD_CUST_ADDR_LINE_1)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_LINE_2,ACUP_OLD_CUST_ADDR_LINE_2)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_LINE_3,ACUP_OLD_CUST_ADDR_LINE_3)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_STATE_CD,ACUP_OLD_CUST_ADDR_STATE_CD)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_COUNTRY_CD,ACUP_OLD_CUST_ADDR_COUNTRY_CD)
                || !foldedSame(s,ACUP_NEW_CUST_ADDR_ZIP,ACUP_OLD_CUST_ADDR_ZIP)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_1A,ACUP_OLD_CUST_PHONE_NUM_1A)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_1B,ACUP_OLD_CUST_PHONE_NUM_1B)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_1C,ACUP_OLD_CUST_PHONE_NUM_1C)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_2A,ACUP_OLD_CUST_PHONE_NUM_2A)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_2B,ACUP_OLD_CUST_PHONE_NUM_2B)
                || !s.same(ACUP_NEW_CUST_PHONE_NUM_2C,ACUP_OLD_CUST_PHONE_NUM_2C)
                || !s.same(ACUP_NEW_CUST_SSN_X,ACUP_OLD_CUST_SSN_X)
                || !foldedSame(s,ACUP_NEW_CUST_GOVT_ISSUED_ID,ACUP_OLD_CUST_GOVT_ISSUED_ID)
                || !s.same(ACUP_NEW_CUST_DOB_YYYY_MM_DD,ACUP_OLD_CUST_DOB_YYYY_MM_DD)
                || !s.same(ACUP_NEW_CUST_EFT_ACCOUNT_ID,ACUP_OLD_CUST_EFT_ACCOUNT_ID)
                || !foldedSame(s,ACUP_NEW_CUST_PRI_HOLDER_IND,ACUP_OLD_CUST_PRI_HOLDER_IND)
                || !s.same(ACUP_NEW_CUST_FICO_SCORE_X,ACUP_OLD_CUST_FICO_SCORE_X)) {
            s.set(CHANGE_HAS_OCCURRED);return;
        }
        s.set(NO_CHANGES_DETECTED);
    }
    private static void edit(AccountMapState s,String label,AccountMapState.Field input,
            AccountMapState.Field scratch,AccountMapState.Rule rule,AccountMapState.Field result,AccountMapState.Field flag) {
        s.put(WS_EDIT_VARIABLE_NAME,label);s.move(scratch,input);s.perform(rule);s.move(flag,result);
    }
    private static void text(AccountMapState s,String label,AccountMapState.Field input,int width,
            AccountMapState.Rule rule,AccountMapState.Field result,AccountMapState.Field flag) {
        s.put(WS_EDIT_VARIABLE_NAME,label);s.move(WS_EDIT_ALPHANUM_ONLY,input);
        s.put(WS_EDIT_ALPHANUM_LENGTH,Integer.toString(width));
        s.perform(rule);s.move(flag,result);
    }
    @CobolSource(program="COACTUPC", paragraph="1200-EDIT-MAP-INPUTS", lines="1429-1680")
    public static void validate(AccountMapState s) {
        s.set(INPUT_OK);
        if(s.test(ACUP_DETAILS_NOT_FETCHED)) {
            account(s);s.low(ACUP_OLD_ACCT_DATA);
            if(s.test(FLG_ACCTFILTER_BLANK))s.set(NO_SEARCH_CRITERIA_RECEIVED);
            return;
        }
        s.set(FOUND_ACCOUNT_DATA);s.set(FOUND_ACCT_IN_MASTER);s.set(FLG_ACCTFILTER_ISVALID);
        s.set(FOUND_CUST_IN_MASTER);s.set(FLG_CUSTFILTER_ISVALID);
        compare(s);
        if(s.test(NO_CHANGES_FOUND) || s.test(ACUP_CHANGES_OK_NOT_CONFIRMED) || s.test(ACUP_CHANGES_OKAYED_AND_DONE)) {
            s.low(WS_NON_KEY_FLAGS);return;
        }
        s.set(ACUP_CHANGES_NOT_OK);
        edit(s,"Account Status",ACUP_NEW_ACTIVE_STATUS,WS_EDIT_YES_NO,YES_NO,WS_EDIT_YES_NO,WS_EDIT_ACCT_STATUS);
        edit(s,"Open Date",ACUP_NEW_OPEN_DATE,WS_EDIT_DATE_CCYYMMDD,DATE,WS_EDIT_DATE_FLGS,WS_EDIT_OPEN_DATE_FLGS);
        edit(s,"Credit Limit",ACUP_NEW_CREDIT_LIMIT_X,WS_EDIT_SIGNED_NUMBER_9V2_X,MONEY,WS_FLG_SIGNED_NUMBER_EDIT,WS_EDIT_CREDIT_LIMIT);
        edit(s,"Expiry Date",ACUP_NEW_EXPIRAION_DATE,WS_EDIT_DATE_CCYYMMDD,DATE,WS_EDIT_DATE_FLGS,WS_EXPIRY_DATE_FLGS);
        edit(s,"Cash Credit Limit",ACUP_NEW_CASH_CREDIT_LIMIT_X,WS_EDIT_SIGNED_NUMBER_9V2_X,MONEY,WS_FLG_SIGNED_NUMBER_EDIT,WS_EDIT_CASH_CREDIT_LIMIT);
        edit(s,"Reissue Date",ACUP_NEW_REISSUE_DATE,WS_EDIT_DATE_CCYYMMDD,DATE,WS_EDIT_DATE_FLGS,WS_EDIT_REISSUE_DATE_FLGS);
        edit(s,"Current Balance",ACUP_NEW_CURR_BAL_X,WS_EDIT_SIGNED_NUMBER_9V2_X,MONEY,WS_FLG_SIGNED_NUMBER_EDIT,WS_EDIT_CURR_BAL);
        edit(s,"Current Cycle Credit Limit",ACUP_NEW_CURR_CYC_CREDIT_X,WS_EDIT_SIGNED_NUMBER_9V2_X,MONEY,WS_FLG_SIGNED_NUMBER_EDIT,WS_EDIT_CURR_CYC_CREDIT);
        edit(s,"Current Cycle Debit Limit",ACUP_NEW_CURR_CYC_DEBIT_X,WS_EDIT_SIGNED_NUMBER_9V2_X,MONEY,WS_FLG_SIGNED_NUMBER_EDIT,WS_EDIT_CURR_CYC_DEBIT);
        s.put(WS_EDIT_VARIABLE_NAME,"SSN");s.perform(SSN);
        edit(s,"Date of Birth",ACUP_NEW_CUST_DOB_YYYY_MM_DD,WS_EDIT_DATE_CCYYMMDD,DATE,WS_EDIT_DATE_FLGS,WS_EDIT_DT_OF_BIRTH_FLGS);
        if(s.test(WS_EDIT_DT_OF_BIRTH_ISVALID)) {
            s.perform(BIRTH);s.move(WS_EDIT_DT_OF_BIRTH_FLGS,WS_EDIT_DATE_FLGS);
        }
        text(s,"FICO Score",ACUP_NEW_CUST_FICO_SCORE_X,3,DIGITS,WS_EDIT_ALPHANUM_ONLY_FLAGS,WS_EDIT_FICO_SCORE_FLGS);
        if(s.test(FLG_FICO_SCORE_ISVALID))s.perform(FICO);
        text(s,"First Name",ACUP_NEW_CUST_FIRST_NAME,25,ALPHA_REQUIRED,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_FIRST_NAME_FLGS);
        text(s,"Middle Name",ACUP_NEW_CUST_MIDDLE_NAME,25,ALPHA_OPTIONAL,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_MIDDLE_NAME_FLGS);
        text(s,"Last Name",ACUP_NEW_CUST_LAST_NAME,25,ALPHA_REQUIRED,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_LAST_NAME_FLGS);
        text(s,"Address Line 1",ACUP_NEW_CUST_ADDR_LINE_1,50,REQUIRED,WS_EDIT_MANDATORY_FLAGS,WS_EDIT_ADDRESS_LINE_1_FLGS);
        text(s,"State",ACUP_NEW_CUST_ADDR_STATE_CD,2,ALPHA_REQUIRED,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_STATE_FLGS);
        if(s.test(FLG_ALPHA_ISVALID))s.perform(STATE);
        text(s,"Zip",ACUP_NEW_CUST_ADDR_ZIP,5,DIGITS,WS_EDIT_ALPHANUM_ONLY_FLAGS,WS_EDIT_ZIPCODE_FLGS);
        text(s,"City",ACUP_NEW_CUST_ADDR_LINE_3,50,ALPHA_REQUIRED,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_CITY_FLGS);
        text(s,"Country",ACUP_NEW_CUST_ADDR_COUNTRY_CD,3,ALPHA_REQUIRED,WS_EDIT_ALPHA_ONLY_FLAGS,WS_EDIT_COUNTRY_FLGS);
        edit(s,"Phone Number 1",ACUP_NEW_CUST_PHONE_NUM_1,WS_EDIT_US_PHONE_NUM,PHONE,WS_EDIT_US_PHONE_NUM_FLGS,WS_EDIT_PHONE_NUM_1_FLGS);
        edit(s,"Phone Number 2",ACUP_NEW_CUST_PHONE_NUM_2,WS_EDIT_US_PHONE_NUM,PHONE,WS_EDIT_US_PHONE_NUM_FLGS,WS_EDIT_PHONE_NUM_2_FLGS);
        text(s,"EFT Account Id",ACUP_NEW_CUST_EFT_ACCOUNT_ID,10,DIGITS,WS_EDIT_ALPHANUM_ONLY_FLAGS,WS_EFT_ACCOUNT_ID_FLGS);
        edit(s,"Primary Card Holder",ACUP_NEW_CUST_PRI_HOLDER_IND,WS_EDIT_YES_NO,YES_NO,WS_EDIT_YES_NO,WS_EDIT_PRI_CARDHOLDER);
        if(s.test(FLG_STATE_ISVALID) && s.test(FLG_ZIPCODE_ISVALID))s.perform(STATE_ZIP);
        if(!s.test(INPUT_ERROR))s.set(ACUP_CHANGES_OK_NOT_CONFIRMED);
    }
}
