package ai.lightyear.carddemo;

import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** Add only the four J5 retirements to the already-retired phone/date group. */
public final class AccountMapModel {
    public static final Map<String,String> RULES=Map.of(
        "1100-RECEIVE-MAP","AccountMapRules",
        "1200-EDIT-MAP-INPUTS","AccountMapRules",
        "1205-COMPARE-OLD-NEW","AccountMapRules",
        "1210-EDIT-ACCOUNT","AccountMapRules");
    public static JsonNode retire(JsonNode original) {
        ObjectNode model=(ObjectNode)AccountPhoneDateModel.retire(original);
        ObjectNode paragraphs=(ObjectNode)model.path("paragraphs");
        ObjectNode nativeRules=(ObjectNode)model.path("native_paragraphs");
        for(var rule:RULES.entrySet()) {
            JsonNode body=paragraphs.path(rule.getKey());
            if(!body.isArray() || body.isEmpty() || nativeRules.has(rule.getKey()))
                throw new IllegalArgumentException("map-retirement:"+rule.getKey());
            paragraphs.remove(rule.getKey());nativeRules.put(rule.getKey(),rule.getValue());
        }
        return model;
    }
}
