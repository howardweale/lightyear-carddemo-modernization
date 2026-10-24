package ai.lightyear.carddemo;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
/** Remove only the nine rendering bodies, preserving the original for the CI oracle. */
public final class AccountRenderModel {
    public static final Map<String,String> RULES=Map.ofEntries(
        Map.entry("3200-SETUP-SCREEN-VARS","AccountRenderRules"),
        Map.entry("3201-SHOW-INITIAL-VALUES","AccountRenderRules"),
        Map.entry("3202-SHOW-ORIGINAL-VALUES","AccountRenderRules"),
        Map.entry("3203-SHOW-UPDATED-VALUES","AccountRenderRules"),
        Map.entry("3250-SETUP-INFOMSG","AccountRenderRules"),
        Map.entry("3300-SETUP-SCREEN-ATTRS","AccountRenderRules"),
        Map.entry("3310-PROTECT-ALL-ATTRS","AccountRenderRules"),
        Map.entry("3320-UNPROTECT-FEW-ATTRS","AccountRenderRules"),
        Map.entry("3390-SETUP-INFOMSG-ATTRS","AccountRenderRules"));
    public static JsonNode retire(JsonNode original) {
        ObjectNode model=(ObjectNode)AccountMapModel.retire(original);
        ObjectNode paragraphs=(ObjectNode)model.path("paragraphs");
        ObjectNode nativeRules=(ObjectNode)model.path("native_paragraphs");
        for(var rule:RULES.entrySet()) {
            JsonNode body=paragraphs.path(rule.getKey());
            if(!body.isArray() || body.isEmpty() || nativeRules.has(rule.getKey()))
                throw new IllegalArgumentException("render-retirement:"+rule.getKey());
            paragraphs.remove(rule.getKey());nativeRules.put(rule.getKey(),rule.getValue());
        }
        return model;
    }
}
