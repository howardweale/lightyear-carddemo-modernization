"""Offline tests for the F0 record boundary; no CMS execution or downloads."""
from decimal import InvalidOperation
import unittest
from tools.cms.f0_smoke import fixed_records, normalize, literal, output_fields


class SmokeBoundaryTests(unittest.TestCase):
    def test_fixed_records_preserve_columns_and_pad(self):
        raw = b"A  B \r\nC\n"
        result = fixed_records(raw, 3)
        self.assertEqual(result, b"A  B ".ljust(80, b" ") + b"C".ljust(80, b" "))
        self.assertEqual(len(result), 160)

    def test_table_overflow_and_width_refused(self):
        for data, capacity in [(b"A\nB\n", 2), (b"x" * 81, 5), (b"", 5)]:
            with self.assertRaises(ValueError):
                fixed_records(data, capacity)

    def test_numeric_hash_domain_is_scale_independent_not_rounded(self):
        self.assertEqual(normalize("+0001.230000000000", True), "1.23")
        self.assertEqual(normalize("-0.000", True), "0")
        self.assertEqual(normalize("-0.000000000001", True), "-0.000000000001")
        self.assertEqual(normalize("  A  ", False), "  A")
        for value in ["NaN", "Infinity"]:
            with self.assertRaises(ValueError):
                normalize(value, True)
        with self.assertRaises(InvalidOperation):
            normalize("*****", True)

    def test_generated_input_cannot_inject_cobol(self):
        self.assertEqual(literal("2021-09-15"), '"20210915"')
        with self.assertRaises(ValueError):
            literal('A". STOP RUN.')

    def test_duplicate_leaf_names_keep_group_identity(self):
        lines = ["01 PPS-DATA."] + [f" 10 TEST-{i} PIC 9(2)." for i in range(50)]
        lines += ["01 PPS-ADDITIONAL-VARIABLES.", " 02 LEFT-GROUP.",
                  "  05 AMOUNT PIC S9(7)V99.", " 02 RIGHT-GROUP.", "  05 AMOUNT PIC S9(7)V99."]
        fields = output_fields(lines)
        self.assertNotEqual(fields[-1]["id"], fields[-2]["id"])
        self.assertEqual(fields[-1]["reference"], "AMOUNT OF RIGHT-GROUP OF PPS-ADDITIONAL-VARIABLES")


if __name__ == "__main__":
    unittest.main()
