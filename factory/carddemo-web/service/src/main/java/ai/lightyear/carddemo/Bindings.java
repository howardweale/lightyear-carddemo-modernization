package ai.lightyear.carddemo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

public final class Bindings {
    public final JsonNode root;
    public final JsonNode data;
    public final String hash;
    public Bindings(Path path,Path plan,JsonMapper json)throws IOException {
        byte[] raw=Files.readAllBytes(path);byte[] mapping=Files.readAllBytes(plan);
        root=json.readTree(raw);data=json.readTree(mapping);
        if(!root.path("schema").asText().equals("carddemo-web-bindings/1") || root.path("screens").size()!=6
            || !data.path("schema").asText().equals("carddemo-data-plan/1")
            || !root.path("upstream_commit").asText().equals(data.path("upstream").path("commit").asText()))throw new IllegalArgumentException("bindings-schema");
        try {MessageDigest d=MessageDigest.getInstance("SHA-256");d.update(raw);d.update((byte)0);d.update(mapping);hash=HexFormat.of().formatHex(d.digest());}
        catch(java.security.GeneralSecurityException e){throw new IllegalStateException(e);}
    }
    public JsonNode program(String name){JsonNode result=root.path("programs").path(name);
        if(result.isMissingNode())throw new IllegalArgumentException("program-outside-slice");return result;}
    public JsonNode screen(String program){for(JsonNode s:root.path("screens"))if(s.path("program").asText().equals(program))return s;
        throw new IllegalArgumentException("no-screen-for-program");}
    public JsonNode mapping(String table){for(JsonNode m:data.path("mappings"))if(m.path("table").asText().equals(table))return m;
        throw new IllegalArgumentException("table-outside-generated-plan");}
    public JsonNode field(String table,String leaf){JsonNode found=null;
        for(JsonNode f:mapping(table).path("fields")){String p=f.path("path").asText();
            if(p.substring(p.lastIndexOf('.')+1).equals(leaf)){if(found!=null)throw new IllegalArgumentException("ambiguous-field");found=f;}}
        if(found==null)throw new IllegalArgumentException("unmapped-field:"+leaf);return found;}
    public String literal(String program,String value){for(JsonNode l:program(program).path("literals"))if(l.path("value").asText().equals(value))return value;
        throw new IllegalArgumentException("unbound-source-literal:"+program);}
}
