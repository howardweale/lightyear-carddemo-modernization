package ai.lightyear.carddemo;
import java.util.Map;
/** Source-ordered COACTVWC record display; transaction/read conditions stay in the service. */
public final class AccountViewRendering {
    private final TypedRecords records;
    public AccountViewRendering(Bindings bindings){records=new TypedRecords(bindings);}
    private enum Field {
        ACCT_ACTIVE_STATUS("acctdata","ACCT-ACTIVE-STATUS"),
        ACCT_CURR_BAL("acctdata","ACCT-CURR-BAL"),
        ACCT_CREDIT_LIMIT("acctdata","ACCT-CREDIT-LIMIT"),
        ACCT_CASH_CREDIT_LIMIT("acctdata","ACCT-CASH-CREDIT-LIMIT"),
        ACCT_CURR_CYC_CREDIT("acctdata","ACCT-CURR-CYC-CREDIT"),
        ACCT_CURR_CYC_DEBIT("acctdata","ACCT-CURR-CYC-DEBIT"),
        ACCT_OPEN_DATE("acctdata","ACCT-OPEN-DATE"),
        ACCT_EXPIRAION_DATE("acctdata","ACCT-EXPIRAION-DATE"),
        ACCT_REISSUE_DATE("acctdata","ACCT-REISSUE-DATE"),
        ACCT_GROUP_ID("acctdata","ACCT-GROUP-ID"),
        CUST_ID("custdata","CUST-ID"),
        CUST_FICO_CREDIT_SCORE("custdata","CUST-FICO-CREDIT-SCORE"),
        CUST_DOB_YYYY_MM_DD("custdata","CUST-DOB-YYYY-MM-DD"),
        CUST_FIRST_NAME("custdata","CUST-FIRST-NAME"),
        CUST_MIDDLE_NAME("custdata","CUST-MIDDLE-NAME"),
        CUST_LAST_NAME("custdata","CUST-LAST-NAME"),
        CUST_ADDR_LINE_1("custdata","CUST-ADDR-LINE-1"),
        CUST_ADDR_LINE_2("custdata","CUST-ADDR-LINE-2"),
        CUST_ADDR_LINE_3("custdata","CUST-ADDR-LINE-3"),
        CUST_ADDR_STATE_CD("custdata","CUST-ADDR-STATE-CD"),
        CUST_ADDR_ZIP("custdata","CUST-ADDR-ZIP"),
        CUST_ADDR_COUNTRY_CD("custdata","CUST-ADDR-COUNTRY-CD"),
        CUST_PHONE_NUM_1("custdata","CUST-PHONE-NUM-1"),
        CUST_PHONE_NUM_2("custdata","CUST-PHONE-NUM-2"),
        CUST_GOVT_ISSUED_ID("custdata","CUST-GOVT-ISSUED-ID"),
        CUST_EFT_ACCOUNT_ID("custdata","CUST-EFT-ACCOUNT-ID"),
        CUST_PRI_CARD_HOLDER_IND("custdata","CUST-PRI-CARD-HOLDER-IND"),
        CUST_SSN("custdata","CUST-SSN");
        final String table,leaf;
        Field(String table,String leaf){this.table=table;this.leaf=leaf;}
    }
    private String value(Field field,Map<String,Object> row){return records.text(field.table,row,field.leaf);}
    private void move(ScreenFrame frame,String target,Field field,Map<String,Object> row){
        String text=value(field,row);var picture=frame.field(target).path("output_picture");
        if(!picture.isMissingNode()&&!picture.isNull())text=ScreenProjection.edited(text,picture.asText());
        frame.set(target,text);
    }
    // The record projection portion is lines 471-523; search key and messages remain in the service.
    @CobolSource(program="COACTVWC", paragraph="1200-SETUP-SCREEN-VARS", lines="460-535")
    public void apply(ScreenFrame frame,Map<String,Object> account,Map<String,Object> customer){
        if(account!=null){
            move(frame,"ACSTTUS",Field.ACCT_ACTIVE_STATUS,account);
            move(frame,"ACURBAL",Field.ACCT_CURR_BAL,account);
            move(frame,"ACRDLIM",Field.ACCT_CREDIT_LIMIT,account);
            move(frame,"ACSHLIM",Field.ACCT_CASH_CREDIT_LIMIT,account);
            move(frame,"ACRCYCR",Field.ACCT_CURR_CYC_CREDIT,account);
            move(frame,"ACRCYDB",Field.ACCT_CURR_CYC_DEBIT,account);
            move(frame,"ADTOPEN",Field.ACCT_OPEN_DATE,account);
            move(frame,"AEXPDT",Field.ACCT_EXPIRAION_DATE,account);
            move(frame,"AREISDT",Field.ACCT_REISSUE_DATE,account);
            move(frame,"AADDGRP",Field.ACCT_GROUP_ID,account);
        }
        if(customer!=null){
            move(frame,"ACSTNUM",Field.CUST_ID,customer);
            String ssn=value(Field.CUST_SSN,customer);
            frame.set("ACSTSSN",ssn.substring(0,3)+"-"+ssn.substring(3,5)+"-"+ssn.substring(5,9));
            move(frame,"ACSTFCO",Field.CUST_FICO_CREDIT_SCORE,customer);
            move(frame,"ACSTDOB",Field.CUST_DOB_YYYY_MM_DD,customer);
            move(frame,"ACSFNAM",Field.CUST_FIRST_NAME,customer);
            move(frame,"ACSMNAM",Field.CUST_MIDDLE_NAME,customer);
            move(frame,"ACSLNAM",Field.CUST_LAST_NAME,customer);
            move(frame,"ACSADL1",Field.CUST_ADDR_LINE_1,customer);
            move(frame,"ACSADL2",Field.CUST_ADDR_LINE_2,customer);
            move(frame,"ACSCITY",Field.CUST_ADDR_LINE_3,customer);
            move(frame,"ACSSTTE",Field.CUST_ADDR_STATE_CD,customer);
            move(frame,"ACSZIPC",Field.CUST_ADDR_ZIP,customer);
            move(frame,"ACSCTRY",Field.CUST_ADDR_COUNTRY_CD,customer);
            move(frame,"ACSPHN1",Field.CUST_PHONE_NUM_1,customer);
            move(frame,"ACSPHN2",Field.CUST_PHONE_NUM_2,customer);
            move(frame,"ACSGOVT",Field.CUST_GOVT_ISSUED_ID,customer);
            move(frame,"ACSEFTC",Field.CUST_EFT_ACCOUNT_ID,customer);
            move(frame,"ACSPFLG",Field.CUST_PRI_CARD_HOLDER_IND,customer);
        }
    }
}
