package ai.lightyear.carddemo;

/** Closed storage vocabulary shared by the phone/date rules and their adapter. */
public interface AccountEditState {
  enum Field {
    WS_CURRENT_DATE_BINARY,
    WS_CURRENT_DATE_YYYYMMDD,
    WS_DATE_FORMAT,
    WS_DIV_BY,
    WS_DIVIDEND,
    WS_EDIT_DATE_BINARY,
    WS_EDIT_DATE_CCYY,
    WS_EDIT_DATE_CCYY_N,
    WS_EDIT_DATE_CCYYMMDD_N,
    WS_EDIT_DATE_DD,
    WS_EDIT_DATE_DD_N,
    WS_EDIT_DATE_MM,
    WS_EDIT_DATE_MM_N,
    WS_EDIT_DATE_YY_N,
    WS_EDIT_US_PHONE_NUMA,
    WS_EDIT_US_PHONE_NUMB,
    WS_EDIT_US_PHONE_NUMC,
    WS_EDIT_VARIABLE_NAME,
    WS_MSG_NO,
    WS_REMAINDER,
    WS_RETURN_MSG,
    WS_SEVERITY,
    WS_SEVERITY_N,
    WS_US_PHONE_AREA_CODE_TO_EDIT
  }

  enum Flag {
    FLG_DAY_BLANK,
    FLG_DAY_ISVALID,
    FLG_DAY_NOT_OK,
    FLG_EDIT_US_PHONEA_BLANK,
    FLG_EDIT_US_PHONEA_ISVALID,
    FLG_EDIT_US_PHONEA_NOT_OK,
    FLG_EDIT_US_PHONEB_BLANK,
    FLG_EDIT_US_PHONEB_ISVALID,
    FLG_EDIT_US_PHONEB_NOT_OK,
    FLG_EDIT_US_PHONEC_BLANK,
    FLG_EDIT_US_PHONEC_ISVALID,
    FLG_EDIT_US_PHONEC_NOT_OK,
    FLG_MONTH_BLANK,
    FLG_MONTH_ISVALID,
    FLG_MONTH_NOT_OK,
    FLG_YEAR_BLANK,
    FLG_YEAR_ISVALID,
    FLG_YEAR_NOT_OK,
    INPUT_ERROR,
    LAST_CENTURY,
    THIS_CENTURY,
    VALID_GENERAL_PURP_CODE,
    WS_31_DAY_MONTH,
    WS_DAY_29,
    WS_DAY_30,
    WS_DAY_31,
    WS_EDIT_DATE_IS_INVALID,
    WS_EDIT_DATE_IS_VALID,
    WS_EDIT_US_PHONE_IS_INVALID,
    WS_EDIT_US_PHONE_IS_VALID,
    WS_FEBRUARY,
    WS_RETURN_MSG_OFF,
    WS_VALID_DAY,
    WS_VALID_MONTH
  }

  String get(Field field);

  void put(Field field, String value);

  boolean test(Flag flag);

  void set(Flag flag);

  void initializeDateResult();

  void checkDateService();

  static AccountEditState bind(SourceEdits storage) {
    return new AccountEditState() {
      public String get(Field field) {
        return storage.get(field.name().replace('_', '-'));
      }

      public void put(Field field, String value) {
        storage.put(field.name().replace('_', '-'), value);
      }

      public boolean test(Flag flag) {
        return storage.condition(flag.name().replace('_', '-'));
      }

      public void set(Flag flag) {
        storage.setCondition(flag.name().replace('_', '-'));
      }

      public void initializeDateResult() {
        storage.initializeDateResult();
      }

      public void checkDateService() {
        storage.checkDateService();
      }
    };
  }
}
