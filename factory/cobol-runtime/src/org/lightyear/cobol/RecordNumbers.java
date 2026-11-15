package org.lightyear.cobol;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.Objects;

/** Slice 1A storage primitives. No arithmetic verbs, layout compiler or candidate admission. */
public final class RecordNumbers {
    private RecordNumbers() {}

    public static final class Refused extends IllegalArgumentException {
        public final String code;
        Refused(String code) { super(code); this.code = code; }
    }

    private static void require(boolean ok, String code) {
        if (!ok) throw new Refused(code);
    }

    public enum Usage { DISPLAY, PACKED, BINARY }
    public enum Sign { UNSIGNED, TRAILING, LEADING, TRAILING_SEPARATE, LEADING_SEPARATE }

    /** Exact stored coefficient and implied scale, including signed zero. Not a field cache. */
    public record Number(BigInteger coefficient, int scale, boolean negativeZero) {
        public Number {
            Objects.requireNonNull(coefficient);
            require(scale >= -18 && scale <= 18, "scale-range");
            require(coefficient.abs().toString().length() <= 18, "coefficient-range");
            require(!negativeZero || coefficient.signum() == 0, "negative-zero");
        }
        public BigDecimal decimal() { return new BigDecimal(coefficient, scale); }
    }

    /** Parsed non-edited numeric PIC. P/V occupy no storage. Expanded precision <=18. */
    public record Pic(int digits, int scale, boolean signed) {
        public Pic {
            require(digits >= 1 && digits <= 18, "pic-digits");
            require(scale >= -18 && scale <= 18, "pic-scale");
            require(Math.max(digits, scale) + Math.max(0, -scale) <= 18, "pic-precision");
        }
        public static Pic parse(String source) {
            require(source != null && source.length() <= 100, "pic-syntax");
            StringBuilder expanded = new StringBuilder();
            for (int i = 0; i < source.length();) {
                char c = source.charAt(i++);
                require("S9VP".indexOf(c) >= 0, "pic-syntax");
                int count = 1;
                if (i < source.length() && source.charAt(i) == '(') {
                    int end = source.indexOf(')', ++i);
                    require(end > i && end - i <= 3 && (c == '9' || c == 'P'), "pic-repeat");
                    String n = source.substring(i, end);
                    require(n.matches("[0-9]{1,3}"), "pic-repeat");
                    count = Integer.parseInt(n);
                    require(count >= 1 && count <= 18, "pic-repeat");
                    i = end + 1;
                }
                require(expanded.length() + count <= 20, "pic-precision");
                expanded.append(String.valueOf(c).repeat(count));
            }
            String text = expanded.toString();
            boolean signed = text.startsWith("S");
            if (signed) text = text.substring(1);
            require(!text.contains("S") && !text.isEmpty(), "pic-syntax");
            int digits = (int) text.chars().filter(c -> c == '9').count();
            int scale;
            if (text.contains("P")) {
                // V is redundant only at the implied point: before leading P, after trailing P.
                if (text.startsWith("V")) text = text.substring(1);
                else if (text.endsWith("V")) text = text.substring(0, text.length() - 1);
                require(text.matches("P+9+") || text.matches("9+P+"), "pic-scaling");
                // Reject V at the opposite end (e.g. P99V or V99P).
                String original = expanded.toString().replaceFirst("^S", "");
                require(!original.contains("V") || original.startsWith("VP")
                        || original.endsWith("PV"), "pic-scaling");
                int ps = text.length() - digits;
                scale = text.startsWith("P") ? digits + ps : -ps;
            } else {
                require(text.matches("9+(V9*)?|V9+"), "pic-syntax");
                int point = text.indexOf('V');
                scale = point < 0 ? 0 : text.length() - point - 1;
            }
            return new Pic(digits, scale, signed);
        }
    }

    public record Descriptor(Pic pic, Usage usage, Sign sign) {
        public Descriptor {
            Objects.requireNonNull(pic); Objects.requireNonNull(usage); Objects.requireNonNull(sign);
            require(pic.signed() == (sign != Sign.UNSIGNED), "sign-pic");
            require(usage == Usage.DISPLAY || sign == Sign.UNSIGNED || sign == Sign.TRAILING,
                    "sign-usage");
        }
        public int width() {
            return switch (usage) {
                case DISPLAY -> pic.digits() + (separate() ? 1 : 0);
                case PACKED -> (pic.digits() + 2) / 2;
                case BINARY -> pic.digits() <= 4 ? 2 : pic.digits() <= 9 ? 4 : 8;
            };
        }
        boolean separate() { return sign == Sign.LEADING_SEPARATE || sign == Sign.TRAILING_SEPARATE; }
        boolean leading() { return sign == Sign.LEADING || sign == Sign.LEADING_SEPARATE; }
    }

    /** One owned arena; no external mutable-array alias. Logical length checked on every access. */
    public static final class Arena {
        private final byte[] bytes;
        private int length;
        public Arena(int capacity) {
            require(capacity >= 1 && capacity <= 1048576, "arena-capacity");
            bytes = new byte[capacity];
        }
        public int capacity() { return bytes.length; }
        public int length() { return length; }
        public void load(byte[] record) {
            require(record != null && record.length <= bytes.length, "record-length");
            Arrays.fill(bytes, (byte) 0);
            System.arraycopy(record, 0, bytes, 0, record.length);
            length = record.length;
        }
        private void range(int offset, int count) {
            require(offset >= 0 && count >= 0 && offset <= length && count <= length - offset,
                    "record-bounds");
        }
        public byte[] snapshot(int offset, int count) {
            range(offset, count);
            return Arrays.copyOfRange(bytes, offset, offset + count);
        }
        public void replace(int offset, byte[] value) {
            Objects.requireNonNull(value);
            range(offset, value.length);
            System.arraycopy(value, 0, bytes, offset, value.length);
        }
        public Field view(int offset, Descriptor descriptor) { return new Field(this, offset, descriptor); }
    }

    public static final class Field {
        private final Arena arena;
        private final int offset;
        private final Descriptor descriptor;
        private Field(Arena arena, int offset, Descriptor descriptor) {
            this.arena = arena; this.offset = offset; this.descriptor = Objects.requireNonNull(descriptor);
            require(offset >= 0 && offset <= arena.capacity()
                    && descriptor.width() <= arena.capacity() - offset, "record-bounds");
        }
        public Number read() { return decode(arena.snapshot(offset, descriptor.width()), descriptor); }
        public boolean isNumeric() { return numericClass(arena.snapshot(offset, descriptor.width()), descriptor); }
        public void writeExact(Number value) {
            // Fully validate before changing any byte. MOVE/arithmetic receiver policy belongs to 1C/2.
            byte[] encoded = encodeExact(value, descriptor);
            arena.replace(offset, encoded);
        }
    }

    private static boolean negativeSign(int nibble) { return nibble == 0xB || nibble == 0xD; }
    private static void signValid(int nibble, boolean signed, boolean classTest) {
        boolean valid = signed ? nibble >= 0xA && nibble <= 0xF : nibble == 0xF;
        if (signed && classTest) valid = nibble == 0xC || nibble == 0xD || nibble == 0xF;
        require(valid, "numeric-sign");
    }
    private static Number value(BigInteger magnitude, boolean negative, Pic pic) {
        return new Number(negative ? magnitude.negate() : magnitude, pic.scale(), negative && magnitude.signum() == 0);
    }

    /** NOPFD numeric access admits valid A-F embedded signs; PRIM class tests use C/D/F. */
    public static Number decode(byte[] bytes, Descriptor descriptor) { return decode(bytes, descriptor, false); }
    private static Number decode(byte[] bytes, Descriptor descriptor, boolean classTest) {
        require(bytes != null && bytes.length == descriptor.width(), "numeric-width");
        Pic pic = descriptor.pic();
        BigInteger magnitude = BigInteger.ZERO;
        boolean negative = false;
        if (descriptor.usage() == Usage.BINARY) {
            BigInteger integer = pic.signed() ? new BigInteger(bytes) : new BigInteger(1, bytes);
            // STD profile: out-of-PIC sending storage is not a qualified valid-data input.
            require(integer.abs().compareTo(BigInteger.TEN.pow(pic.digits())) < 0, "binary-outside-pic");
            return new Number(integer, pic.scale(), false);
        }
        if (descriptor.usage() == Usage.PACKED) {
            int pad = bytes.length * 2 - pic.digits() - 1;
            if (pad == 1) require((bytes[0] & 0xF0) == 0, "packed-padding");
            for (int i = pad; i < bytes.length * 2 - 1; i++) {
                int digit = (bytes[i / 2] >> (i % 2 == 0 ? 4 : 0)) & 15;
                require(digit <= 9, "numeric-digit");
                magnitude = magnitude.multiply(BigInteger.TEN).add(BigInteger.valueOf(digit));
            }
            int sign = bytes[bytes.length - 1] & 15;
            signValid(sign, pic.signed(), classTest);
            negative = negativeSign(sign);
        } else {
            int first = descriptor.sign() == Sign.LEADING_SEPARATE ? 1 : 0;
            if (descriptor.separate()) {
                int sign = bytes[descriptor.leading() ? 0 : bytes.length - 1] & 255;
                require(sign == 0x4E || sign == 0x60, "numeric-sign"); // cp037 '+' and '-'
                negative = sign == 0x60;
            }
            int signIndex = descriptor.leading() ? first : first + pic.digits() - 1;
            for (int i = first; i < first + pic.digits(); i++) {
                int digit = bytes[i] & 15;
                int zone = (bytes[i] & 255) >> 4;
                require(digit <= 9, "numeric-digit");
                if (pic.signed() && !descriptor.separate() && i == signIndex) {
                    signValid(zone, true, classTest);
                    negative = negativeSign(zone);
                } else require(zone == 0xF, "numeric-zone");
                magnitude = magnitude.multiply(BigInteger.TEN).add(BigInteger.valueOf(digit));
            }
        }
        return value(magnitude, negative, pic);
    }

    public static boolean numericClass(byte[] bytes, Descriptor descriptor) {
        // Bounds/descriptor errors are API misuse, not a COBOL false class predicate.
        require(descriptor.usage() != Usage.BINARY, "class-usage");
        require(bytes != null && bytes.length == descriptor.width(), "numeric-width");
        // IBM class rules cited by this profile do not settle a nonzero unused pad.
        if (descriptor.usage() == Usage.PACKED && descriptor.pic().digits() % 2 == 0)
            require((bytes[0] & 0xF0) == 0, "packed-padding-class-unsupported");
        try { decode(bytes, descriptor, true); return true; }
        catch (Refused e) { return false; }
    }

    /** Exact representability only: no hidden rounding, decimal truncation or size-error hook. */
    public static byte[] encodeExact(Number number, Descriptor descriptor) {
        Objects.requireNonNull(number);
        Pic pic = descriptor.pic();
        BigInteger coefficient;
        try { coefficient = number.decimal().setScale(pic.scale(), RoundingMode.UNNECESSARY).unscaledValue(); }
        catch (ArithmeticException e) { throw new Refused("inexact-encode"); }
        boolean negative = coefficient.signum() < 0 || number.negativeZero();
        require(pic.signed() || !negative, "unsigned-negative");
        BigInteger magnitude = coefficient.abs();
        require(magnitude.compareTo(BigInteger.TEN.pow(pic.digits())) < 0, "encode-overflow");
        byte[] result = new byte[descriptor.width()];
        if (descriptor.usage() == Usage.BINARY) {
            // Two's-complement big endian; an integer binary zero has no sign bit to preserve.
            byte[] raw = coefficient.toByteArray();
            require(raw.length <= result.length, "binary-width");
            Arrays.fill(result, coefficient.signum() < 0 ? (byte) 0xFF : (byte) 0);
            System.arraycopy(raw, 0, result, result.length - raw.length, raw.length);
            return result;
        }
        String digits = magnitude.toString();
        digits = "0".repeat(pic.digits() - digits.length()) + digits;
        if (descriptor.usage() == Usage.PACKED) {
            int pad = result.length * 2 - pic.digits() - 1;
            for (int i = 0; i < digits.length(); i++) {
                int nibble = i + pad;
                result[nibble / 2] |= (byte) ((digits.charAt(i) - '0') << (nibble % 2 == 0 ? 4 : 0));
            }
            result[result.length - 1] |= (byte) (!pic.signed() ? 0xF : negative ? 0xD : 0xC);
        } else {
            int first = descriptor.sign() == Sign.LEADING_SEPARATE ? 1 : 0;
            for (int i = 0; i < digits.length(); i++) result[first + i] = (byte) (0xF0 | (digits.charAt(i) - '0'));
            if (descriptor.separate()) result[descriptor.leading() ? 0 : result.length - 1] = (byte) (negative ? 0x60 : 0x4E);
            else if (pic.signed()) {
                int at = descriptor.leading() ? 0 : result.length - 1;
                result[at] = (byte) ((result[at] & 15) | (negative ? 0xD0 : 0xC0));
            }
        }
        return result;
    }
}
