package ai.lightyear.carddemo;
import static ai.lightyear.carddemo.AccountRenderState.*;
import static ai.lightyear.carddemo.AccountRenderState.Value.*;
import static ai.lightyear.carddemo.AccountRenderState.ScreenField.*;
/** COACTUPC screen values and attributes, in source order. */
public final class AccountRenderRules {
    private AccountRenderRules() {}
    @CobolSource(program="COACTUPC", paragraph="3200-SETUP-SCREEN-VARS", lines="2698-2729")
    public static void values(AccountRenderState s) {
        if(s.test(Flag.CDEMO_PGM_ENTER))return;
        if(s.accountZero() && s.valid(Edit.ACCTFILTER))s.low(ACCTSID);
        else s.move(ACCTSID,CC_ACCT_ID);
        if(s.test(Flag.ACUP_DETAILS_NOT_FETCHED) || s.accountZero())initial(s);
        else if(s.test(Flag.ACUP_SHOW_DETAILS))original(s);
        else if(s.test(Flag.ACUP_CHANGES_MADE))updated(s);
        else original(s);
    }
    @CobolSource(program="COACTUPC", paragraph="3201-SHOW-INITIAL-VALUES", lines="2731-2785")
    public static void initial(AccountRenderState s) {
        s.low(ACSTTUS);
        s.low(ACRDLIM);
        s.low(ACURBAL);
        s.low(ACSHLIM);
        s.low(ACRCYCR);
        s.low(ACRCYDB);
        s.low(OPNYEAR);
        s.low(OPNMON);
        s.low(OPNDAY);
        s.low(EXPYEAR);
        s.low(EXPMON);
        s.low(EXPDAY);
        s.low(RISYEAR);
        s.low(RISMON);
        s.low(RISDAY);
        s.low(AADDGRP);
        s.low(ACSTNUM);
        s.low(ACTSSN1);
        s.low(ACTSSN2);
        s.low(ACTSSN3);
        s.low(ACSTFCO);
        s.low(DOBYEAR);
        s.low(DOBMON);
        s.low(DOBDAY);
        s.low(ACSFNAM);
        s.low(ACSMNAM);
        s.low(ACSLNAM);
        s.low(ACSADL1);
        s.low(ACSADL2);
        s.low(ACSCITY);
        s.low(ACSSTTE);
        s.low(ACSZIPC);
        s.low(ACSCTRY);
        s.low(ACSPH1A);
        s.low(ACSPH1B);
        s.low(ACSPH1C);
        s.low(ACSPH2A);
        s.low(ACSPH2B);
        s.low(ACSPH2C);
        s.low(ACSGOVT);
        s.low(ACSEFTC);
        s.low(ACSPFLG);
    }
    @CobolSource(program="COACTUPC", paragraph="3202-SHOW-ORIGINAL-VALUES", lines="2787-2869")
    public static void original(AccountRenderState s) {
        s.clearNonKeyFlags();s.set(Flag.PROMPT_FOR_CHANGES);
        if(s.test(Flag.FOUND_ACCT_IN_MASTER) || s.test(Flag.FOUND_CUST_IN_MASTER)) {
            s.move(ACSTTUS,ACUP_OLD_ACTIVE_STATUS);
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_OLD_CURR_BAL_N);
            s.move(ACURBAL,WS_EDIT_CURRENCY_9_2_F);
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_OLD_CREDIT_LIMIT_N);
            s.move(ACRDLIM,WS_EDIT_CURRENCY_9_2_F);
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_OLD_CASH_CREDIT_LIMIT_N);
            s.move(ACSHLIM,WS_EDIT_CURRENCY_9_2_F);
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_OLD_CURR_CYC_CREDIT_N);
            s.move(ACRCYCR,WS_EDIT_CURRENCY_9_2_F);
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_OLD_CURR_CYC_DEBIT_N);
            s.move(ACRCYDB,WS_EDIT_CURRENCY_9_2_F);
            s.move(OPNYEAR,ACUP_OLD_OPEN_YEAR);
            s.move(OPNMON,ACUP_OLD_OPEN_MON);
            s.move(OPNDAY,ACUP_OLD_OPEN_DAY);
            s.move(EXPYEAR,ACUP_OLD_EXP_YEAR);
            s.move(EXPMON,ACUP_OLD_EXP_MON);
            s.move(EXPDAY,ACUP_OLD_EXP_DAY);
            s.move(RISYEAR,ACUP_OLD_REISSUE_YEAR);
            s.move(RISMON,ACUP_OLD_REISSUE_MON);
            s.move(RISDAY,ACUP_OLD_REISSUE_DAY);
            s.move(AADDGRP,ACUP_OLD_GROUP_ID);
        }
        if(s.test(Flag.FOUND_CUST_IN_MASTER)) {
            s.move(ACSTNUM,ACUP_OLD_CUST_ID_X);
            s.slice(ACTSSN1,ACUP_OLD_CUST_SSN_X,1,3);
            s.slice(ACTSSN2,ACUP_OLD_CUST_SSN_X,4,2);
            s.slice(ACTSSN3,ACUP_OLD_CUST_SSN_X,6,4);
            s.move(ACSTFCO,ACUP_OLD_CUST_FICO_SCORE_X);
            s.move(DOBYEAR,ACUP_OLD_CUST_DOB_YEAR);
            s.move(DOBMON,ACUP_OLD_CUST_DOB_MON);
            s.move(DOBDAY,ACUP_OLD_CUST_DOB_DAY);
            s.move(ACSFNAM,ACUP_OLD_CUST_FIRST_NAME);
            s.move(ACSMNAM,ACUP_OLD_CUST_MIDDLE_NAME);
            s.move(ACSLNAM,ACUP_OLD_CUST_LAST_NAME);
            s.move(ACSADL1,ACUP_OLD_CUST_ADDR_LINE_1);
            s.move(ACSADL2,ACUP_OLD_CUST_ADDR_LINE_2);
            s.move(ACSCITY,ACUP_OLD_CUST_ADDR_LINE_3);
            s.move(ACSSTTE,ACUP_OLD_CUST_ADDR_STATE_CD);
            s.move(ACSZIPC,ACUP_OLD_CUST_ADDR_ZIP);
            s.move(ACSCTRY,ACUP_OLD_CUST_ADDR_COUNTRY_CD);
            s.slice(ACSPH1A,ACUP_OLD_CUST_PHONE_NUM_1,2,3);
            s.slice(ACSPH1B,ACUP_OLD_CUST_PHONE_NUM_1,6,3);
            s.slice(ACSPH1C,ACUP_OLD_CUST_PHONE_NUM_1,10,4);
            s.slice(ACSPH2A,ACUP_OLD_CUST_PHONE_NUM_2,2,3);
            s.slice(ACSPH2B,ACUP_OLD_CUST_PHONE_NUM_2,6,3);
            s.slice(ACSPH2C,ACUP_OLD_CUST_PHONE_NUM_2,10,4);
            s.move(ACSGOVT,ACUP_OLD_CUST_GOVT_ISSUED_ID);
            s.move(ACSEFTC,ACUP_OLD_CUST_EFT_ACCOUNT_ID);
            s.move(ACSPFLG,ACUP_OLD_CUST_PRI_HOLDER_IND);
        }
    }
    @CobolSource(program="COACTUPC", paragraph="3203-SHOW-UPDATED-VALUES", lines="2870-2953")
    public static void updated(AccountRenderState s) {
        s.move(ACSTTUS,ACUP_NEW_ACTIVE_STATUS);
        if(s.valid(Edit.CRED_LIMIT)) {
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_NEW_CREDIT_LIMIT_N);
            s.move(ACRDLIM,WS_EDIT_CURRENCY_9_2_F);
        } else s.move(ACRDLIM,ACUP_NEW_CREDIT_LIMIT_X);
        if(s.valid(Edit.CASH_CREDIT_LIMIT)) {
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_NEW_CASH_CREDIT_LIMIT_N);
            s.move(ACSHLIM,WS_EDIT_CURRENCY_9_2_F);
        } else s.move(ACSHLIM,ACUP_NEW_CASH_CREDIT_LIMIT_X);
        if(s.valid(Edit.CURR_BAL)) {
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_NEW_CURR_BAL_N);
            s.move(ACURBAL,WS_EDIT_CURRENCY_9_2_F);
        } else s.move(ACURBAL,ACUP_NEW_CURR_BAL_X);
        if(s.valid(Edit.CURR_CYC_CREDIT)) {
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_NEW_CURR_CYC_CREDIT_N);
            s.move(ACRCYCR,WS_EDIT_CURRENCY_9_2_F);
        } else s.move(ACRCYCR,ACUP_NEW_CURR_CYC_CREDIT_X);
        if(s.valid(Edit.CURR_CYC_DEBIT)) {
            s.move(WS_EDIT_CURRENCY_9_2_F,ACUP_NEW_CURR_CYC_DEBIT_N);
            s.move(ACRCYDB,WS_EDIT_CURRENCY_9_2_F);
        } else s.move(ACRCYDB,ACUP_NEW_CURR_CYC_DEBIT_X);
        s.move(OPNYEAR,ACUP_NEW_OPEN_YEAR);
        s.move(OPNMON,ACUP_NEW_OPEN_MON);
        s.move(OPNDAY,ACUP_NEW_OPEN_DAY);
        s.move(EXPYEAR,ACUP_NEW_EXP_YEAR);
        s.move(EXPMON,ACUP_NEW_EXP_MON);
        s.move(EXPDAY,ACUP_NEW_EXP_DAY);
        s.move(RISYEAR,ACUP_NEW_REISSUE_YEAR);
        s.move(RISMON,ACUP_NEW_REISSUE_MON);
        s.move(RISDAY,ACUP_NEW_REISSUE_DAY);
        s.move(AADDGRP,ACUP_NEW_GROUP_ID);
        s.move(ACSTNUM,ACUP_NEW_CUST_ID_X);
        s.move(ACTSSN1,ACUP_NEW_CUST_SSN_1);
        s.move(ACTSSN2,ACUP_NEW_CUST_SSN_2);
        s.move(ACTSSN3,ACUP_NEW_CUST_SSN_3);
        s.move(ACSTFCO,ACUP_NEW_CUST_FICO_SCORE_X);
        s.move(DOBYEAR,ACUP_NEW_CUST_DOB_YEAR);
        s.move(DOBMON,ACUP_NEW_CUST_DOB_MON);
        s.move(DOBDAY,ACUP_NEW_CUST_DOB_DAY);
        s.move(ACSFNAM,ACUP_NEW_CUST_FIRST_NAME);
        s.move(ACSMNAM,ACUP_NEW_CUST_MIDDLE_NAME);
        s.move(ACSLNAM,ACUP_NEW_CUST_LAST_NAME);
        s.move(ACSADL1,ACUP_NEW_CUST_ADDR_LINE_1);
        s.move(ACSADL2,ACUP_NEW_CUST_ADDR_LINE_2);
        s.move(ACSCITY,ACUP_NEW_CUST_ADDR_LINE_3);
        s.move(ACSSTTE,ACUP_NEW_CUST_ADDR_STATE_CD);
        s.move(ACSZIPC,ACUP_NEW_CUST_ADDR_ZIP);
        s.move(ACSCTRY,ACUP_NEW_CUST_ADDR_COUNTRY_CD);
        s.move(ACSPH1A,ACUP_NEW_CUST_PHONE_NUM_1A);
        s.move(ACSPH1B,ACUP_NEW_CUST_PHONE_NUM_1B);
        s.move(ACSPH1C,ACUP_NEW_CUST_PHONE_NUM_1C);
        s.move(ACSPH2A,ACUP_NEW_CUST_PHONE_NUM_2A);
        s.move(ACSPH2B,ACUP_NEW_CUST_PHONE_NUM_2B);
        s.move(ACSPH2C,ACUP_NEW_CUST_PHONE_NUM_2C);
        s.move(ACSGOVT,ACUP_NEW_CUST_GOVT_ISSUED_ID);
        s.move(ACSEFTC,ACUP_NEW_CUST_EFT_ACCOUNT_ID);
        s.move(ACSPFLG,ACUP_NEW_CUST_PRI_HOLDER_IND);
    }
    @CobolSource(program="COACTUPC", paragraph="3250-SETUP-INFOMSG", lines="2955-2985")
    public static void information(AccountRenderState s) {
        if(s.test(Flag.CDEMO_PGM_ENTER) || s.test(Flag.ACUP_DETAILS_NOT_FETCHED))s.set(Flag.PROMPT_FOR_SEARCH_KEYS);
        else if(s.test(Flag.ACUP_SHOW_DETAILS) || s.test(Flag.ACUP_CHANGES_NOT_OK))s.set(Flag.PROMPT_FOR_CHANGES);
        else if(s.test(Flag.ACUP_CHANGES_OK_NOT_CONFIRMED))s.set(Flag.PROMPT_FOR_CONFIRMATION);
        else if(s.test(Flag.ACUP_CHANGES_OKAYED_AND_DONE))s.set(Flag.CONFIRM_UPDATE_SUCCESS);
        else if(s.test(Flag.ACUP_CHANGES_OKAYED_LOCK_ERROR) || s.test(Flag.ACUP_CHANGES_OKAYED_BUT_FAILED))s.set(Flag.INFORM_FAILURE);
        else if(s.test(Flag.WS_NO_INFO_MESSAGE))s.set(Flag.PROMPT_FOR_SEARCH_KEYS);
        s.move(INFOMSG,WS_INFO_MSG);s.move(ERRMSG,WS_RETURN_MSG);
    }
    @CobolSource(program="COACTUPC", paragraph="3300-SETUP-SCREEN-ATTRS", lines="2986-3439")
    public static void attributes(AccountRenderState s) {
        protect(s);
        if(s.test(Flag.ACUP_DETAILS_NOT_FETCHED))s.attribute(ACCTSID,Attribute.DFHBMFSE);
        else if(s.test(Flag.ACUP_SHOW_DETAILS) || s.test(Flag.ACUP_CHANGES_NOT_OK))unprotect(s);
        else if(!s.test(Flag.ACUP_CHANGES_OK_NOT_CONFIRMED) && !s.test(Flag.ACUP_CHANGES_OKAYED_AND_DONE))s.attribute(ACCTSID,Attribute.DFHBMFSE);
        if(s.test(Flag.FOUND_ACCOUNT_DATA) || s.test(Flag.NO_CHANGES_DETECTED))s.cursor(ACSTTUS);
        else if(s.bad(Edit.ACCTFILTER) || s.blank(Edit.ACCTFILTER))s.cursor(ACCTSID);
        else if(s.bad(Edit.ACCT_STATUS) || s.blank(Edit.ACCT_STATUS))s.cursor(ACSTTUS);
        else if(s.bad(Edit.OPEN_YEAR) || s.blank(Edit.OPEN_YEAR))s.cursor(OPNYEAR);
        else if(s.bad(Edit.OPEN_MONTH) || s.blank(Edit.OPEN_MONTH))s.cursor(OPNMON);
        else if(s.bad(Edit.OPEN_DAY) || s.blank(Edit.OPEN_DAY))s.cursor(OPNDAY);
        else if(s.bad(Edit.CRED_LIMIT) || s.blank(Edit.CRED_LIMIT))s.cursor(ACRDLIM);
        else if(s.bad(Edit.EXPIRY_YEAR) || s.blank(Edit.EXPIRY_YEAR))s.cursor(EXPYEAR);
        else if(s.bad(Edit.EXPIRY_MONTH) || s.blank(Edit.EXPIRY_MONTH))s.cursor(EXPMON);
        else if(s.bad(Edit.EXPIRY_DAY) || s.blank(Edit.EXPIRY_DAY))s.cursor(EXPDAY);
        else if(s.bad(Edit.CASH_CREDIT_LIMIT) || s.blank(Edit.CASH_CREDIT_LIMIT))s.cursor(ACSHLIM);
        else if(s.bad(Edit.REISSUE_YEAR) || s.blank(Edit.REISSUE_YEAR))s.cursor(RISYEAR);
        else if(s.bad(Edit.REISSUE_MONTH) || s.blank(Edit.REISSUE_MONTH))s.cursor(RISMON);
        else if(s.bad(Edit.REISSUE_DAY) || s.blank(Edit.REISSUE_DAY))s.cursor(RISDAY);
        else if(s.bad(Edit.CURR_BAL) || s.blank(Edit.CURR_BAL))s.cursor(ACURBAL);
        else if(s.bad(Edit.CURR_CYC_CREDIT) || s.blank(Edit.CURR_CYC_CREDIT))s.cursor(ACRCYCR);
        else if(s.bad(Edit.CURR_CYC_DEBIT) || s.blank(Edit.CURR_CYC_DEBIT))s.cursor(ACRCYDB);
        else if(s.bad(Edit.EDIT_US_SSN_PART1) || s.blank(Edit.EDIT_US_SSN_PART1))s.cursor(ACTSSN1);
        else if(s.bad(Edit.EDIT_US_SSN_PART2) || s.blank(Edit.EDIT_US_SSN_PART2))s.cursor(ACTSSN2);
        else if(s.bad(Edit.EDIT_US_SSN_PART3) || s.blank(Edit.EDIT_US_SSN_PART3))s.cursor(ACTSSN3);
        else if(s.bad(Edit.DT_OF_BIRTH_YEAR) || s.blank(Edit.DT_OF_BIRTH_YEAR))s.cursor(DOBYEAR);
        else if(s.bad(Edit.DT_OF_BIRTH_MONTH) || s.blank(Edit.DT_OF_BIRTH_MONTH))s.cursor(DOBMON);
        else if(s.bad(Edit.DT_OF_BIRTH_DAY) || s.blank(Edit.DT_OF_BIRTH_DAY))s.cursor(DOBDAY);
        else if(s.bad(Edit.FICO_SCORE) || s.blank(Edit.FICO_SCORE))s.cursor(ACSTFCO);
        else if(s.bad(Edit.FIRST_NAME) || s.blank(Edit.FIRST_NAME))s.cursor(ACSFNAM);
        else if(s.bad(Edit.MIDDLE_NAME))s.cursor(ACSMNAM);
        else if(s.bad(Edit.LAST_NAME) || s.blank(Edit.LAST_NAME))s.cursor(ACSLNAM);
        else if(s.bad(Edit.ADDRESS_LINE_1) || s.blank(Edit.ADDRESS_LINE_1))s.cursor(ACSADL1);
        else if(s.bad(Edit.STATE) || s.blank(Edit.STATE))s.cursor(ACSSTTE);
        else if(s.bad(Edit.ZIPCODE) || s.blank(Edit.ZIPCODE))s.cursor(ACSZIPC);
        else if(s.bad(Edit.CITY) || s.blank(Edit.CITY))s.cursor(ACSCITY);
        else if(s.bad(Edit.COUNTRY) || s.blank(Edit.COUNTRY))s.cursor(ACSCTRY);
        else if(s.bad(Edit.PHONE_NUM_1A) || s.blank(Edit.PHONE_NUM_1A))s.cursor(ACSPH1A);
        else if(s.bad(Edit.PHONE_NUM_1B) || s.blank(Edit.PHONE_NUM_1B))s.cursor(ACSPH1B);
        else if(s.bad(Edit.PHONE_NUM_1C) || s.blank(Edit.PHONE_NUM_1C))s.cursor(ACSPH1C);
        else if(s.bad(Edit.PHONE_NUM_2A) || s.blank(Edit.PHONE_NUM_2A))s.cursor(ACSPH2A);
        else if(s.bad(Edit.PHONE_NUM_2B) || s.blank(Edit.PHONE_NUM_2B))s.cursor(ACSPH2B);
        else if(s.bad(Edit.PHONE_NUM_2C) || s.blank(Edit.PHONE_NUM_2C))s.cursor(ACSPH2C);
        else if(s.bad(Edit.EFT_ACCOUNT_ID) || s.blank(Edit.EFT_ACCOUNT_ID))s.cursor(ACSEFTC);
        else if(s.bad(Edit.PRI_CARDHOLDER) || s.blank(Edit.PRI_CARDHOLDER))s.cursor(ACSPFLG);
        else s.cursor(ACCTSID);
        if(s.fromCardList())s.color(ACCTSID,Color.DFHDFCOL);
        if(s.bad(Edit.ACCTFILTER))s.color(ACCTSID,Color.DFHRED);
        if(s.blank(Edit.ACCTFILTER) && s.test(Flag.CDEMO_PGM_REENTER)) {s.text(ACCTSID,"*");s.color(ACCTSID,Color.DFHRED);}
        if(s.test(Flag.ACUP_DETAILS_NOT_FETCHED) || s.blank(Edit.ACCTFILTER) || s.bad(Edit.ACCTFILTER))return;
        if((s.bad(Edit.ACCT_STATUS) || s.blank(Edit.ACCT_STATUS)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSTTUS,Color.DFHRED);
            if(s.blank(Edit.ACCT_STATUS))s.text(ACSTTUS,"*");
        }
        if((s.bad(Edit.OPEN_YEAR) || s.blank(Edit.OPEN_YEAR)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(OPNYEAR,Color.DFHRED);
            if(s.blank(Edit.OPEN_YEAR))s.text(OPNYEAR,"*");
        }
        if((s.bad(Edit.OPEN_MONTH) || s.blank(Edit.OPEN_MONTH)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(OPNMON,Color.DFHRED);
            if(s.blank(Edit.OPEN_MONTH))s.text(OPNMON,"*");
        }
        if((s.bad(Edit.OPEN_DAY) || s.blank(Edit.OPEN_DAY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(OPNDAY,Color.DFHRED);
            if(s.blank(Edit.OPEN_DAY))s.text(OPNDAY,"*");
        }
        if((s.bad(Edit.CRED_LIMIT) || s.blank(Edit.CRED_LIMIT)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACRDLIM,Color.DFHRED);
            if(s.blank(Edit.CRED_LIMIT))s.text(ACRDLIM,"*");
        }
        if((s.bad(Edit.EXPIRY_YEAR) || s.blank(Edit.EXPIRY_YEAR)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(EXPYEAR,Color.DFHRED);
            if(s.blank(Edit.EXPIRY_YEAR))s.text(EXPYEAR,"*");
        }
        if((s.bad(Edit.EXPIRY_MONTH) || s.blank(Edit.EXPIRY_MONTH)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(EXPMON,Color.DFHRED);
            if(s.blank(Edit.EXPIRY_MONTH))s.text(EXPMON,"*");
        }
        if((s.bad(Edit.EXPIRY_DAY) || s.blank(Edit.EXPIRY_DAY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(EXPDAY,Color.DFHRED);
            if(s.blank(Edit.EXPIRY_DAY))s.text(EXPDAY,"*");
        }
        if((s.bad(Edit.CASH_CREDIT_LIMIT) || s.blank(Edit.CASH_CREDIT_LIMIT)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSHLIM,Color.DFHRED);
            if(s.blank(Edit.CASH_CREDIT_LIMIT))s.text(ACSHLIM,"*");
        }
        if((s.bad(Edit.REISSUE_YEAR) || s.blank(Edit.REISSUE_YEAR)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(RISYEAR,Color.DFHRED);
            if(s.blank(Edit.REISSUE_YEAR))s.text(RISYEAR,"*");
        }
        if((s.bad(Edit.REISSUE_MONTH) || s.blank(Edit.REISSUE_MONTH)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(RISMON,Color.DFHRED);
            if(s.blank(Edit.REISSUE_MONTH))s.text(RISMON,"*");
        }
        if((s.bad(Edit.REISSUE_DAY) || s.blank(Edit.REISSUE_DAY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(RISDAY,Color.DFHRED);
            if(s.blank(Edit.REISSUE_DAY))s.text(RISDAY,"*");
        }
        if((s.bad(Edit.CURR_BAL) || s.blank(Edit.CURR_BAL)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACURBAL,Color.DFHRED);
            if(s.blank(Edit.CURR_BAL))s.text(ACURBAL,"*");
        }
        if((s.bad(Edit.CURR_CYC_CREDIT) || s.blank(Edit.CURR_CYC_CREDIT)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACRCYCR,Color.DFHRED);
            if(s.blank(Edit.CURR_CYC_CREDIT))s.text(ACRCYCR,"*");
        }
        if((s.bad(Edit.CURR_CYC_DEBIT) || s.blank(Edit.CURR_CYC_DEBIT)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACRCYDB,Color.DFHRED);
            if(s.blank(Edit.CURR_CYC_DEBIT))s.text(ACRCYDB,"*");
        }
        if((s.bad(Edit.EDIT_US_SSN_PART1) || s.blank(Edit.EDIT_US_SSN_PART1)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACTSSN1,Color.DFHRED);
            if(s.blank(Edit.EDIT_US_SSN_PART1))s.text(ACTSSN1,"*");
        }
        if((s.bad(Edit.EDIT_US_SSN_PART2) || s.blank(Edit.EDIT_US_SSN_PART2)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACTSSN2,Color.DFHRED);
            if(s.blank(Edit.EDIT_US_SSN_PART2))s.text(ACTSSN2,"*");
        }
        if((s.bad(Edit.EDIT_US_SSN_PART3) || s.blank(Edit.EDIT_US_SSN_PART3)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACTSSN3,Color.DFHRED);
            if(s.blank(Edit.EDIT_US_SSN_PART3))s.text(ACTSSN3,"*");
        }
        if((s.bad(Edit.DT_OF_BIRTH_YEAR) || s.blank(Edit.DT_OF_BIRTH_YEAR)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(DOBYEAR,Color.DFHRED);
            if(s.blank(Edit.DT_OF_BIRTH_YEAR))s.text(DOBYEAR,"*");
        }
        if((s.bad(Edit.DT_OF_BIRTH_MONTH) || s.blank(Edit.DT_OF_BIRTH_MONTH)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(DOBMON,Color.DFHRED);
            if(s.blank(Edit.DT_OF_BIRTH_MONTH))s.text(DOBMON,"*");
        }
        if((s.bad(Edit.DT_OF_BIRTH_DAY) || s.blank(Edit.DT_OF_BIRTH_DAY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(DOBDAY,Color.DFHRED);
            if(s.blank(Edit.DT_OF_BIRTH_DAY))s.text(DOBDAY,"*");
        }
        if((s.bad(Edit.FICO_SCORE) || s.blank(Edit.FICO_SCORE)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSTFCO,Color.DFHRED);
            if(s.blank(Edit.FICO_SCORE))s.text(ACSTFCO,"*");
        }
        if((s.bad(Edit.FIRST_NAME) || s.blank(Edit.FIRST_NAME)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSFNAM,Color.DFHRED);
            if(s.blank(Edit.FIRST_NAME))s.text(ACSFNAM,"*");
        }
        if((s.bad(Edit.MIDDLE_NAME) || s.blank(Edit.MIDDLE_NAME)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSMNAM,Color.DFHRED);
            if(s.blank(Edit.MIDDLE_NAME))s.text(ACSMNAM,"*");
        }
        if((s.bad(Edit.LAST_NAME) || s.blank(Edit.LAST_NAME)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSLNAM,Color.DFHRED);
            if(s.blank(Edit.LAST_NAME))s.text(ACSLNAM,"*");
        }
        if((s.bad(Edit.ADDRESS_LINE_1) || s.blank(Edit.ADDRESS_LINE_1)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSADL1,Color.DFHRED);
            if(s.blank(Edit.ADDRESS_LINE_1))s.text(ACSADL1,"*");
        }
        if((s.bad(Edit.STATE) || s.blank(Edit.STATE)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSSTTE,Color.DFHRED);
            if(s.blank(Edit.STATE))s.text(ACSSTTE,"*");
        }
        if((s.bad(Edit.ADDRESS_LINE_2) || s.blank(Edit.ADDRESS_LINE_2)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSADL2,Color.DFHRED);
            if(s.blank(Edit.ADDRESS_LINE_2))s.text(ACSADL2,"*");
        }
        if((s.bad(Edit.ZIPCODE) || s.blank(Edit.ZIPCODE)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSZIPC,Color.DFHRED);
            if(s.blank(Edit.ZIPCODE))s.text(ACSZIPC,"*");
        }
        if((s.bad(Edit.CITY) || s.blank(Edit.CITY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSCITY,Color.DFHRED);
            if(s.blank(Edit.CITY))s.text(ACSCITY,"*");
        }
        if((s.bad(Edit.COUNTRY) || s.blank(Edit.COUNTRY)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSCTRY,Color.DFHRED);
            if(s.blank(Edit.COUNTRY))s.text(ACSCTRY,"*");
        }
        if((s.bad(Edit.PHONE_NUM_1A) || s.blank(Edit.PHONE_NUM_1A)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH1A,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_1A))s.text(ACSPH1A,"*");
        }
        if((s.bad(Edit.PHONE_NUM_1B) || s.blank(Edit.PHONE_NUM_1B)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH1B,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_1B))s.text(ACSPH1B,"*");
        }
        if((s.bad(Edit.PHONE_NUM_1C) || s.blank(Edit.PHONE_NUM_1C)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH1C,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_1C))s.text(ACSPH1C,"*");
        }
        if((s.bad(Edit.PHONE_NUM_2A) || s.blank(Edit.PHONE_NUM_2A)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH2A,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_2A))s.text(ACSPH2A,"*");
        }
        if((s.bad(Edit.PHONE_NUM_2B) || s.blank(Edit.PHONE_NUM_2B)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH2B,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_2B))s.text(ACSPH2B,"*");
        }
        if((s.bad(Edit.PHONE_NUM_2C) || s.blank(Edit.PHONE_NUM_2C)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPH2C,Color.DFHRED);
            if(s.blank(Edit.PHONE_NUM_2C))s.text(ACSPH2C,"*");
        }
        if((s.bad(Edit.PRI_CARDHOLDER) || s.blank(Edit.PRI_CARDHOLDER)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSPFLG,Color.DFHRED);
            if(s.blank(Edit.PRI_CARDHOLDER))s.text(ACSPFLG,"*");
        }
        if((s.bad(Edit.EFT_ACCOUNT_ID) || s.blank(Edit.EFT_ACCOUNT_ID)) && s.test(Flag.CDEMO_PGM_REENTER)) {
            s.color(ACSEFTC,Color.DFHRED);
            if(s.blank(Edit.EFT_ACCOUNT_ID))s.text(ACSEFTC,"*");
        }
    }
    @CobolSource(program="COACTUPC", paragraph="3310-PROTECT-ALL-ATTRS", lines="3441-3498")
    public static void protect(AccountRenderState s) {
        s.attribute(ACCTSID,Attribute.DFHBMPRF);
        s.attribute(ACSTTUS,Attribute.DFHBMPRF);
        s.attribute(ACRDLIM,Attribute.DFHBMPRF);
        s.attribute(ACSHLIM,Attribute.DFHBMPRF);
        s.attribute(ACURBAL,Attribute.DFHBMPRF);
        s.attribute(ACRCYCR,Attribute.DFHBMPRF);
        s.attribute(ACRCYDB,Attribute.DFHBMPRF);
        s.attribute(OPNYEAR,Attribute.DFHBMPRF);
        s.attribute(OPNMON,Attribute.DFHBMPRF);
        s.attribute(OPNDAY,Attribute.DFHBMPRF);
        s.attribute(EXPYEAR,Attribute.DFHBMPRF);
        s.attribute(EXPMON,Attribute.DFHBMPRF);
        s.attribute(EXPDAY,Attribute.DFHBMPRF);
        s.attribute(RISYEAR,Attribute.DFHBMPRF);
        s.attribute(RISMON,Attribute.DFHBMPRF);
        s.attribute(RISDAY,Attribute.DFHBMPRF);
        s.attribute(AADDGRP,Attribute.DFHBMPRF);
        s.attribute(ACSTNUM,Attribute.DFHBMPRF);
        s.attribute(ACTSSN1,Attribute.DFHBMPRF);
        s.attribute(ACTSSN2,Attribute.DFHBMPRF);
        s.attribute(ACTSSN3,Attribute.DFHBMPRF);
        s.attribute(ACSTFCO,Attribute.DFHBMPRF);
        s.attribute(DOBYEAR,Attribute.DFHBMPRF);
        s.attribute(DOBMON,Attribute.DFHBMPRF);
        s.attribute(DOBDAY,Attribute.DFHBMPRF);
        s.attribute(ACSFNAM,Attribute.DFHBMPRF);
        s.attribute(ACSMNAM,Attribute.DFHBMPRF);
        s.attribute(ACSLNAM,Attribute.DFHBMPRF);
        s.attribute(ACSADL1,Attribute.DFHBMPRF);
        s.attribute(ACSADL2,Attribute.DFHBMPRF);
        s.attribute(ACSCITY,Attribute.DFHBMPRF);
        s.attribute(ACSSTTE,Attribute.DFHBMPRF);
        s.attribute(ACSZIPC,Attribute.DFHBMPRF);
        s.attribute(ACSCTRY,Attribute.DFHBMPRF);
        s.attribute(ACSPH1A,Attribute.DFHBMPRF);
        s.attribute(ACSPH1B,Attribute.DFHBMPRF);
        s.attribute(ACSPH1C,Attribute.DFHBMPRF);
        s.attribute(ACSPH2A,Attribute.DFHBMPRF);
        s.attribute(ACSPH2B,Attribute.DFHBMPRF);
        s.attribute(ACSPH2C,Attribute.DFHBMPRF);
        s.attribute(ACSGOVT,Attribute.DFHBMPRF);
        s.attribute(ACSEFTC,Attribute.DFHBMPRF);
        s.attribute(ACSPFLG,Attribute.DFHBMPRF);
        s.attribute(INFOMSG,Attribute.DFHBMPRF);
    }
    @CobolSource(program="COACTUPC", paragraph="3320-UNPROTECT-FEW-ATTRS", lines="3500-3564")
    public static void unprotect(AccountRenderState s) {
        s.attribute(ACSTTUS,Attribute.DFHBMFSE);
        s.attribute(ACRDLIM,Attribute.DFHBMFSE);
        s.attribute(ACSHLIM,Attribute.DFHBMFSE);
        s.attribute(ACURBAL,Attribute.DFHBMFSE);
        s.attribute(ACRCYCR,Attribute.DFHBMFSE);
        s.attribute(ACRCYDB,Attribute.DFHBMFSE);
        s.attribute(OPNYEAR,Attribute.DFHBMFSE);
        s.attribute(OPNMON,Attribute.DFHBMFSE);
        s.attribute(OPNDAY,Attribute.DFHBMFSE);
        s.attribute(EXPYEAR,Attribute.DFHBMFSE);
        s.attribute(EXPMON,Attribute.DFHBMFSE);
        s.attribute(EXPDAY,Attribute.DFHBMFSE);
        s.attribute(RISYEAR,Attribute.DFHBMFSE);
        s.attribute(RISMON,Attribute.DFHBMFSE);
        s.attribute(RISDAY,Attribute.DFHBMFSE);
        s.attribute(DOBYEAR,Attribute.DFHBMFSE);
        s.attribute(DOBMON,Attribute.DFHBMFSE);
        s.attribute(DOBDAY,Attribute.DFHBMFSE);
        s.attribute(AADDGRP,Attribute.DFHBMFSE);
        s.attribute(ACSTNUM,Attribute.DFHBMPRF);
        s.attribute(ACTSSN1,Attribute.DFHBMFSE);
        s.attribute(ACTSSN2,Attribute.DFHBMFSE);
        s.attribute(ACTSSN3,Attribute.DFHBMFSE);
        s.attribute(ACSTFCO,Attribute.DFHBMFSE);
        s.attribute(ACSFNAM,Attribute.DFHBMFSE);
        s.attribute(ACSMNAM,Attribute.DFHBMFSE);
        s.attribute(ACSLNAM,Attribute.DFHBMFSE);
        s.attribute(ACSADL1,Attribute.DFHBMFSE);
        s.attribute(ACSADL2,Attribute.DFHBMFSE);
        s.attribute(ACSCITY,Attribute.DFHBMFSE);
        s.attribute(ACSSTTE,Attribute.DFHBMFSE);
        s.attribute(ACSZIPC,Attribute.DFHBMFSE);
        s.attribute(ACSCTRY,Attribute.DFHBMPRF);
        s.attribute(ACSPH1A,Attribute.DFHBMFSE);
        s.attribute(ACSPH1B,Attribute.DFHBMFSE);
        s.attribute(ACSPH1C,Attribute.DFHBMFSE);
        s.attribute(ACSPH2A,Attribute.DFHBMFSE);
        s.attribute(ACSPH2B,Attribute.DFHBMFSE);
        s.attribute(ACSPH2C,Attribute.DFHBMFSE);
        s.attribute(ACSGOVT,Attribute.DFHBMFSE);
        s.attribute(ACSEFTC,Attribute.DFHBMFSE);
        s.attribute(ACSPFLG,Attribute.DFHBMFSE);
        s.attribute(INFOMSG,Attribute.DFHBMPRF);
    }
    @CobolSource(program="COACTUPC", paragraph="3390-SETUP-INFOMSG-ATTRS", lines="3566-3586")
    public static void informationAttributes(AccountRenderState s) {
        s.attribute(INFOMSG,s.test(Flag.WS_NO_INFO_MESSAGE)?Attribute.DFHBMDAR:Attribute.DFHBMASB);
        if(s.test(Flag.ACUP_CHANGES_MADE) && !s.test(Flag.ACUP_CHANGES_OKAYED_AND_DONE))s.attribute(FKEY12,Attribute.DFHBMASB);
        if(s.test(Flag.PROMPT_FOR_CONFIRMATION)) {s.attribute(FKEY05,Attribute.DFHBMASB);s.attribute(FKEY12,Attribute.DFHBMASB);}
    }
}
