package ai.lightyear.carddemo.codec;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.Map;

public final class ZonedDecimal {

    private static final String POSITIVE = "{ABCDEFGHI";
    private static final String NEGATIVE = "}JKLMNOPQR";
    private static final Map<Character, Integer> POSITIVE_VALUES = values(POSITIVE);
    private static final Map<Character, Integer> NEGATIVE_VALUES = values(NEGATIVE);

    private ZonedDecimal() {
    }

    public static BigDecimal decode(String text, int scale) {
        if (text == null || text.isEmpty()) {
            throw new IllegalArgumentException("Empty zoned-decimal value");
        }
        char last = text.charAt(text.length() - 1);
        int sign;
        int digit;
        if (POSITIVE_VALUES.containsKey(last)) {
            sign = 1;
            digit = POSITIVE_VALUES.get(last);
        } else if (NEGATIVE_VALUES.containsKey(last)) {
            sign = -1;
            digit = NEGATIVE_VALUES.get(last);
        } else if (Character.isDigit(last)) {
            sign = 1;
            digit = last - '0';
        } else {
            throw new IllegalArgumentException("Invalid zoned-decimal overpunch: " + last);
        }
        String digits = text.substring(0, text.length() - 1) + digit;
        if (!digits.chars().allMatch(Character::isDigit)) {
            throw new IllegalArgumentException("Invalid zoned-decimal digits: " + text);
        }
        return new BigDecimal(new BigInteger(digits).multiply(BigInteger.valueOf(sign)), scale);
    }

    public static String encode(BigDecimal value, int width, int scale) {
        BigDecimal normalized = value.setScale(scale, RoundingMode.DOWN);
        BigInteger scaled = normalized.abs().movePointRight(scale).toBigIntegerExact();
        String digits = String.format("%0" + width + "d", scaled);
        if (digits.length() > width) {
            throw new IllegalArgumentException(value + " overflows zoned decimal width " + width);
        }
        int last = digits.charAt(digits.length() - 1) - '0';
        char overpunch = normalized.signum() < 0 ? NEGATIVE.charAt(last) : POSITIVE.charAt(last);
        return digits.substring(0, digits.length() - 1) + overpunch;
    }

    private static Map<Character, Integer> values(String characters) {
        var result = new java.util.HashMap<Character, Integer>();
        for (int index = 0; index < characters.length(); index++) {
            result.put(characters.charAt(index), index);
        }
        return Map.copyOf(result);
    }
}

