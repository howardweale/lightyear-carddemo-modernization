package org.lightyear.cobol;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import org.lightyear.cobol.RecordNumbers.Arena;
import org.lightyear.cobol.RecordNumbers.Descriptor;
import org.lightyear.cobol.RecordNumbers.Field;
import org.lightyear.cobol.RecordNumbers.Number;
import org.lightyear.cobol.RecordNumbers.Pic;
import org.lightyear.cobol.RecordNumbers.Refused;
import org.lightyear.cobol.RecordNumbers.Sign;
import org.lightyear.cobol.RecordNumbers.Usage;

/** CI-only harness. All expected bytes are literals supplied in independently derived vectors. */
public final class RecordNumbersTest {
    private static int checks;
    private static void equal(Object expected, Object actual) {
        checks++;
        if (!expected.equals(actual)) throw new AssertionError("vector-or-invariant-mismatch");
    }
    private static void refuses(String code, Runnable action) {
        try { action.run(); }
        catch (Refused e) { equal(code, e.code); return; }
        throw new AssertionError("expected-refusal");
    }
    private static byte[] hex(String value) { return HexFormat.of().parseHex(value); }
    private static String hex(byte[] value) { return HexFormat.of().formatHex(value); }
    private static Number number(String value, int scale, boolean negativeZero) {
        return new Number(new BigInteger(value), scale, negativeZero);
    }
    private static void invariants() {
        Descriptor unsigned = new Descriptor(Pic.parse("9(2)"), Usage.DISPLAY, Sign.UNSIGNED);
        Arena arena = new Arena(6);
        Field beforeLoad = arena.view(1, unsigned);
        refuses("record-bounds", beforeLoad::read);
        refuses("record-bounds", beforeLoad::isNumeric);
        refuses("record-bounds", () -> beforeLoad.writeExact(number("12", 0, false)));
        refuses("record-bounds", () -> arena.view(5, unsigned));
        refuses("record-bounds", () -> arena.view(Integer.MAX_VALUE, unsigned));
        byte[] input = hex("aaf1f2bbcccc");
        arena.load(input);
        equal("12", beforeLoad.read().coefficient().toString());
        input[1] = 0;
        Field first = arena.view(1, unsigned);
        Field alias = arena.view(1, unsigned);
        equal("12", first.read().coefficient().toString());
        alias.writeExact(number("34", 0, false));
        equal("34", first.read().coefficient().toString());
        equal("aaf3f4bbcccc", hex(arena.snapshot(0, 6)));
        byte[] snapshot = arena.snapshot(0, 6);
        snapshot[1] = 0;
        equal("34", first.read().coefficient().toString());
        refuses("encode-overflow", () -> first.writeExact(number("100", 0, false)));
        equal("aaf3f4bbcccc", hex(arena.snapshot(0, 6)));
        refuses("inexact-encode", () -> first.writeExact(number("345", 1, false)));
        equal("34", first.read().coefficient().toString());
        arena.load(hex("f9"));
        refuses("record-bounds", first::read);
        refuses("record-bounds", () -> arena.snapshot(Integer.MAX_VALUE, 2));
        refuses("record-bounds", () -> arena.snapshot(0, Integer.MAX_VALUE));
        refuses("record-bounds", () -> arena.replace(1, hex("00")));
        refuses("record-bounds", () -> arena.view(-1, unsigned));
        refuses("record-length", () -> arena.load(new byte[7]));
        equal(1, arena.length());
        arena.load(hex("f1f2f3f4"));
        equal("23", first.read().coefficient().toString());
        // Reload invalidates any old logical extent without retaining old tail data.
        equal(4, arena.length());
        equal(6, arena.capacity());
        refuses("arena-capacity", () -> new Arena(0));
        refuses("arena-capacity", () -> new Arena(1048577));
        equal(new Pic(3, 2, true), Pic.parse("S9V99"));
        equal(new Pic(3, 5, false), Pic.parse("VP(2)9(3)"));
        equal(new Pic(3, -2, false), Pic.parse("9(3)P(2)V"));
        refuses("pic-scaling", () -> Pic.parse("9P9"));
        refuses("pic-scaling", () -> Pic.parse("P99V"));
        refuses("pic-scaling", () -> Pic.parse("V99P"));
        refuses("pic-syntax", () -> Pic.parse("99V9V9"));
        refuses("pic-syntax", () -> Pic.parse("9S9"));
        equal(new Pic(9, 0, false), Pic.parse("9(09)"));
        equal(new Pic(11, 2, true), Pic.parse("S9(09)V99"));
        equal(new Pic(18, 0, false), Pic.parse("9(018)"));
        refuses("pic-repeat", () -> Pic.parse("9(00)"));
        refuses("pic-repeat", () -> Pic.parse("9(019)"));
        refuses("pic-repeat", () -> Pic.parse("9(0)"));
        refuses("pic-repeat", () -> Pic.parse("9(19)"));
        refuses("pic-syntax", () -> Pic.parse("9(2)."));
        refuses("pic-scale", () -> Pic.parse("P9(18)"));
        refuses("sign-pic", () -> new Descriptor(Pic.parse("S99"), Usage.DISPLAY, Sign.UNSIGNED));
        refuses("sign-usage", () -> new Descriptor(Pic.parse("S99"), Usage.BINARY, Sign.LEADING));
        refuses("numeric-width", () -> RecordNumbers.numericClass(hex("f1"), unsigned));
        equal(2, new Descriptor(Pic.parse("S9(4)"), Usage.BINARY, Sign.TRAILING).width());
        equal(4, new Descriptor(Pic.parse("S9(9)"), Usage.BINARY, Sign.TRAILING).width());
        equal(8, new Descriptor(Pic.parse("S9(18)"), Usage.BINARY, Sign.TRAILING).width());
        Descriptor evenPacked = new Descriptor(Pic.parse("S99"), Usage.PACKED, Sign.TRAILING);
        refuses("packed-padding-class-unsupported", () -> RecordNumbers.numericClass(hex("100c"), evenPacked));
        refuses("packed-padding", () -> RecordNumbers.decode(hex("100c"), evenPacked));
        equal(true, RecordNumbers.numericClass(hex("000c"), evenPacked));
        // Valid nonpreferred arithmetic signs and PRIM class signs must not be conflated.
        Descriptor signed = new Descriptor(Pic.parse("S9"), Usage.PACKED, Sign.TRAILING);
        for (int nibble = 10; nibble <= 15; nibble++) {
            byte[] raw = {(byte) (0x10 | nibble)};
            equal(nibble == 11 || nibble == 13 ? "-1" : "1", RecordNumbers.decode(raw, signed).coefficient().toString());
            equal(nibble == 12 || nibble == 13 || nibble == 15, RecordNumbers.numericClass(raw, signed));
        }
    }
    private static String run(String[] columns) {
        Descriptor descriptor = new Descriptor(Pic.parse(columns[1]), Usage.valueOf(columns[2]), Sign.valueOf(columns[3]));
        return switch (columns[0]) {
            case "decode" -> {
                Number value = RecordNumbers.decode(hex(columns[4]), descriptor);
                yield value.coefficient() + ":" + value.scale() + ":" + value.negativeZero();
            }
            case "encode" -> hex(RecordNumbers.encodeExact(number(columns[5], Integer.parseInt(columns[6]), Boolean.parseBoolean(columns[7])), descriptor));
            case "numeric-class" -> Boolean.toString(RecordNumbers.numericClass(hex(columns[4]), descriptor));
            case "arena-alias", "arena-short-read" -> {
                Arena arena = new Arena(Integer.parseInt(columns[10]));
                arena.load(hex(columns[4]));
                int offset = Integer.parseInt(columns[9]);
                Field first = arena.view(offset, descriptor);
                if (columns[0].equals("arena-short-read")) {
                    arena.load(hex(columns[11]));
                    first.read();
                } else {
                    Field alias = arena.view(offset, descriptor);
                    alias.writeExact(number(columns[5], Integer.parseInt(columns[6]), Boolean.parseBoolean(columns[7])));
                    // The first field observes the same bytes; no independent scalar state.
                    equal(alias.read(), first.read());
                }
                yield hex(arena.snapshot(0, arena.length()));
            }
            default -> throw new AssertionError("protocol-operation");
        };
    }
    public static void main(String[] args) throws Exception {
        invariants();
        int vectors = 0;
        int mismatches = 0;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                String[] columns = line.split("\t", -1);
                if (columns.length != 13 || !columns[12].matches("[A-Z][A-Z0-9_-]{0,63}"))
                    throw new AssertionError("protocol-columns");
                String actual;
                try { actual = run(columns); }
                catch (Refused e) { actual = "REFUSED:" + e.code; }
                catch (RuntimeException | AssertionError e) { actual = "UNEXPECTED_VECTOR_FAULT"; }
                checks++;
                if (!columns[8].equals(actual)) {
                    System.err.println("codec-vector-mismatch id=" + columns[12]);
                    mismatches++;
                }
                vectors++;
            }
        }
        if (vectors == 0) throw new AssertionError("empty-vector-suite");
        if (mismatches != 0) throw new AssertionError("codec-vector-mismatches=" + mismatches);
        System.out.println("codec-vectors-match vectors=" + vectors + " checks=" + checks);
    }
}
