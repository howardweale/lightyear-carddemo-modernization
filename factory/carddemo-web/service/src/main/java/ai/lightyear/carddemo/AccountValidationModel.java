package ai.lightyear.carddemo;

import java.util.List;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** Production-only model selection; the pinned generator and test oracle stay unchanged. */
public final class AccountValidationModel {
    private AccountValidationModel() {}

    public static JsonNode forProduction(JsonNode source) {
        if(source==null || !source.isObject() || !source.path("paragraphs").isObject())
            throw new IllegalArgumentException("location-model-shape");
        if(source.has("native_paragraphs") && !source.path("native_paragraphs").isObject())
            throw new IllegalArgumentException("location-native-shape");
        ObjectNode copy=(ObjectNode)source.deepCopy();
        ObjectNode paragraphs=(ObjectNode)copy.path("paragraphs");
        ObjectNode nativeRules=copy.has("native_paragraphs")
            ? (ObjectNode)copy.path("native_paragraphs") : copy.putObject("native_paragraphs");
        for(String name:List.of("1270-EDIT-US-STATE-CD","1280-EDIT-US-STATE-ZIP-CD")) {
            if(!paragraphs.has(name))throw new IllegalArgumentException("missing-location-paragraph:"+name);
            if(!paragraphs.path(name).isArray() || paragraphs.path(name).isEmpty())
                throw new IllegalArgumentException("location-paragraph-shape:"+name);
            if(nativeRules.has(name))throw new IllegalArgumentException("location-already-native:"+name);
            paragraphs.remove(name);
            nativeRules.put(name,"AccountLocationRules");
        }
        return copy;
    }
}
