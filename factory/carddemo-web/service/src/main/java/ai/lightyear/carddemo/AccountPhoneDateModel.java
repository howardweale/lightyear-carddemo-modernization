package ai.lightyear.carddemo;

import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** Retire this bounded group without changing the frozen binding generator. */
public final class AccountPhoneDateModel {
    public static final Map<String,String> RULES=Map.of(
        "1260-EDIT-US-PHONE-NUM","AccountPhoneRules",
        "EDIT-DATE-CCYYMMDD","AccountDateRules",
        "EDIT-DATE-OF-BIRTH","AccountDateRules");
    public static JsonNode retire(JsonNode original) {
        ObjectNode model=(ObjectNode)original.deepCopy();
        ObjectNode paragraphs=(ObjectNode)model.path("paragraphs");
        ObjectNode nativeRules=(ObjectNode)model.path("native_paragraphs");
        for(var rule:RULES.entrySet()) {
            JsonNode body=paragraphs.path(rule.getKey());
            if(!body.isArray() || body.isEmpty() || nativeRules.has(rule.getKey()))
                throw new IllegalArgumentException("phone-date-retirement:"+rule.getKey());
            paragraphs.remove(rule.getKey());nativeRules.put(rule.getKey(),rule.getValue());
        }
        return model;
    }
}
