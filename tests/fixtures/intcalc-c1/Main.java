// Public plumbing fixture, NOT an INTCALC conversion. No model-generated code.
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;

public final class Main {
    public static void main(String[] args) throws Exception {
        var options = new HashMap<String, String>();
        for (int i = 0; i < args.length; i += 2) options.put(args[i], args[i + 1]);
        Path input = Path.of(options.get("--input-dir"));
        Path output = Path.of(options.get("--output-dir"));
        Files.copy(input.resolve("ACCTFILE.bin"), output.resolve("ACCTFILE.bin"));
        Files.write(output.resolve("TRANSACT.bin"), new byte[0]);
    }
}
