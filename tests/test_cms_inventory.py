import io
import unittest
import zipfile

from tools.cms.inventory import inventory, source_members


def package(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


class CmsInventoryTests(unittest.TestCase):
    def test_nested_self_extracting_zip_is_inventoried_without_execution(self):
        nested = b"MZ-not-executed" + package({"payload.cbl": b"abc"})
        rows = inventory(package({"installer.exe": nested}))
        self.assertIn({"path": "installer.exe!/payload.cbl", "size_bytes": 3}, rows)

    def test_program_id_and_bound_call_do_not_depend_on_filename(self):
        source = ("000100 IDENTIFICATION DIVISION.\n"
                  "000200 PROGRAM-ID. TARGET.\n"
                  "000300 01 CALLEE PIC X(8) VALUE 'OTHER'.\n"
                  "000400 PROCEDURE DIVISION.\n"
                  "000500     CALL CALLEE.\n"
                  "000600*    CALL 'IGNORED'.\n")
        rows = source_members(package({"ODDNAME": source, "README": "       CALL MADEUP"}))
        self.assertEqual(rows[0]["program_id"], "TARGET")
        self.assertEqual(rows[0]["calls"], ["OTHER"])
        self.assertEqual(rows[1]["calls"], [])


if __name__ == "__main__":
    unittest.main()
