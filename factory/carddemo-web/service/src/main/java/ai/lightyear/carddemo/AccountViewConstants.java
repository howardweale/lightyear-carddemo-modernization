package ai.lightyear.carddemo;

import tools.jackson.databind.JsonNode;

/** Generated source constants are loaded and validated once at service startup. */
public record AccountViewConstants(String menuProgram,String menuTransaction,String mapset,String map) {
    public static AccountViewConstants load(Bindings bindings){
        JsonNode values=bindings.program("COACTVWC").path("constants");
        return new AccountViewConstants(required(values,"LIT-MENUPGM"),required(values,"LIT-MENUTRANID"),
            required(values,"LIT-THISMAPSET"),required(values,"LIT-THISMAP"));
    }
    private static String required(JsonNode values,String name){
        JsonNode value=values.path(name);
        if(!value.isString() || value.asText().isEmpty())throw new IllegalArgumentException("account-view-constant:"+name);
        return value.asText();
    }
}
