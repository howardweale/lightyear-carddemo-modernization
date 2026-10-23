package ai.lightyear.carddemo;

import java.util.Arrays;
import java.util.Objects;
import tools.jackson.databind.JsonNode;

/** Closed copybook vocabulary for COACTVWC orchestration; no storage conversion. */
public final class CommonArea {
    public enum Field {
        PREVIOUS_PROGRAM("CDEMO-FROM-PROGRAM"),
        PREVIOUS_TRANSACTION("CDEMO-FROM-TRANID"),
        NEXT_PROGRAM("CDEMO-TO-PROGRAM"),
        NEXT_TRANSACTION("CDEMO-TO-TRANID"),
        USER_TYPE("CDEMO-USER-TYPE"),
        PROGRAM_CONTEXT("CDEMO-PGM-CONTEXT"),
        LAST_MAPSET("CDEMO-LAST-MAPSET"),
        LAST_MAP("CDEMO-LAST-MAP"),
        ACCOUNT_ID("CDEMO-ACCT-ID"),
        CUSTOMER_ID("CDEMO-CUST-ID"),
        CARD_NUMBER("CDEMO-CARD-NUM");
        private final String sourceName;
        Field(String sourceName){this.sourceName=sourceName;}
    }
    private final Commarea storage;
    public CommonArea(Commarea storage){this.storage=Objects.requireNonNull(storage);}
    public static void validateLayout(JsonNode layout){
        Commarea.requireFields(layout,Arrays.stream(Field.values()).map(field->field.sourceName).toArray(String[]::new));
    }
    public String get(Field field){return storage.get(field.sourceName);}
    public void set(Field field,String value){storage.set(field.sourceName,value);}
    public void move(Field field,String value){storage.move(field.sourceName,value);}
}
