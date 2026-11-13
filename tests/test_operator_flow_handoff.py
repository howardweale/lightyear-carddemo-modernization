"""CI-only bounded archive refusals, not authentic producer/admission fixtures."""
from hashlib import sha256
from io import BytesIO
import os,stat,unittest,zipfile
from tools.ci.operator_flow_handoff import read_public_archive,strict_json,LIMITS,_expected

def archive(entries):
    target=BytesIO()
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as output:
        for name,value in entries:output.writestr(name,value)
    return target.getvalue()

class HandoffArchiveRefusals(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.entries=[(name,b'public synthetic bytes') for name in LIMITS]
    def decode(self,entries):
        raw=archive(entries);return read_public_archive(raw,sha256(raw).hexdigest())
    def test_bounded_bytes_are_returned_without_authority_interpretation(self):
        self.assertEqual(self.decode(self.entries),dict(self.entries))
    def test_missing_member_refused(self):
        with self.assertRaisesRegex(ValueError,'exact-files'):self.decode(self.entries[:-1])
    def test_extra_member_refused(self):
        with self.assertRaisesRegex(ValueError,'exact-files'):self.decode(self.entries+[('unexpected',b'x')])
    def test_duplicate_member_refused(self):
        with self.assertRaisesRegex(ValueError,'exact-files'):self.decode(self.entries[:-1]+[self.entries[0]])
    def test_traversal_absolute_backslash_and_subdirectory_names_refused(self):
        for name in ('../public.pem','/public.pem','dir/public.pem','dir\\public.pem'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'exact-files'):
                self.decode([(name,b'x')]+self.entries[1:])
    def test_symlink_member_refused(self):
        info=zipfile.ZipInfo(self.entries[0][0]);info.create_system=3
        info.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaisesRegex(ValueError,'regular-unencrypted'):
            self.decode([(info,b'target')]+self.entries[1:])
    def test_file_limit_refused(self):
        entries=[(name,b'x'*(LIMITS[name]+1) if name=='public.pem' else value) for name,value in self.entries]
        with self.assertRaisesRegex(ValueError,'entry-size'):self.decode(entries)
    def test_wrong_archive_digest_refused(self):
        raw=archive(self.entries)
        with self.assertRaisesRegex(ValueError,'archive-digest'):read_public_archive(raw,'0'*64)
    def test_duplicate_and_nonfinite_json_refused(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'):
            with self.assertRaises(ValueError):strict_json(raw)
    def test_boolean_or_proof_supplied_expectations_refused(self):
        row=dict(executable='a'*40,producer_run_id=12,artifact_id=34,archive_sha256='b'*64)
        with self.assertRaisesRegex(ValueError,'expectation-values'):_expected(dict(row,producer_run_id=True))
        with self.assertRaisesRegex(ValueError,'expectation-fields'):_expected(dict(row,proof={}))
