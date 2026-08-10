package ai.lightyear.carddemo.io;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.function.Function;

public final class DatasetIo {

    private DatasetIo() {
    }

    public static <T> List<T> read(Path path, Function<String, T> parser) throws IOException {
        if (!Files.isRegularFile(path)) {
            throw new IOException("Required dataset does not exist: " + path);
        }
        return Files.readAllLines(path, StandardCharsets.US_ASCII).stream().map(parser).toList();
    }

    public static <T> void write(Path path, List<T> records, Function<T, String> renderer, int length)
            throws IOException {
        Files.createDirectories(path.getParent());
        List<String> lines = records.stream().map(renderer).peek(record -> {
            if (record.length() != length) {
                throw new IllegalArgumentException(
                        "Rendered record has length " + record.length() + "; expected " + length);
            }
        }).toList();
        Files.write(
                path,
                lines,
                StandardCharsets.US_ASCII,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }
}

