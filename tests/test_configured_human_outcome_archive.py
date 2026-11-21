"""CI-only original ZIP decoding checks; inert bytes never proof or authority."""
import hashlib,os,stat,struct,unittest,warnings,zipfile
from io import BytesIO
from lightyear_factory.contracts import ContractError
from tools.ci.configured_outcome_inventory import _limits
from tools.ci.configured_outcome_archive import decode_outcome_archive,read_outcome_archive
@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only archive checks')
class OutcomeArchiveBoundary(unittest.TestCase):
    def archive(self,changes=None,omit=None,extra=None,compression=zipfile.ZIP_STORED):
        data={name:b'inert-public-byte-marker' for name in _limits()}
        if changes:data.update(changes)
        if omit:del data[omit]
        result=BytesIO()
        with zipfile.ZipFile(result,'w',compression=compression) as archive:
            for name,value in data.items():archive.writestr(name,value)
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning);archive.writestr(*extra)
        return result.getvalue(),data
    def decode(self,raw):return decode_outcome_archive(raw,hashlib.sha256(raw).hexdigest())
    def test_original_stored_and_deflated_bytes_return_unchanged(self):
        for compression in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
            raw,data=self.archive(compression=compression);self.assertEqual(self.decode(raw),data)
    def test_inert_archive_never_passes_native_inventory_entry(self):
        raw,_=self.archive()
        with self.assertRaises((ContractError,ValueError)):
            read_outcome_archive(raw,hashlib.sha256(raw).hexdigest(),{})
    def test_wrong_independent_archive_digest_refuses(self):
        raw,_=self.archive()
        with self.assertRaises(ContractError):decode_outcome_archive(raw,'0'*64)
    def test_missing_extra_duplicate_and_traversal_names_refuse(self):
        for options in ({'omit':'summary.json'},{'extra':('unexpected.json',b'x')},
                        {'extra':('summary.json',b'x')},{'omit':'summary.json','extra':('../summary.json',b'x')}):
            raw,_=self.archive(**options)
            with self.assertRaises(ContractError):self.decode(raw)
    def test_empty_oversize_and_high_ratio_entry_refuse(self):
        for value,compression in ((b'',zipfile.ZIP_STORED),(b'x'*1048577,zipfile.ZIP_STORED),
                                  (b'x'*1048576,zipfile.ZIP_DEFLATED)):
            raw,_=self.archive({'summary.json':value},compression=compression)
            with self.assertRaises(ContractError):self.decode(raw)
    def test_symlink_and_directory_modes_refuse(self):
        for mode in (stat.S_IFLNK|0o777,stat.S_IFDIR|0o755):
            raw,data=self.archive();result=BytesIO()
            with zipfile.ZipFile(result,'w') as archive:
                for name,value in data.items():
                    info=zipfile.ZipInfo(name);info.create_system=3
                    info.external_attr=((mode if name=='summary.json' else stat.S_IFREG|0o644)<<16)
                    archive.writestr(info,value)
            with self.assertRaises(ContractError):self.decode(result.getvalue())
    def test_crc_corruption_and_truncation_refuse(self):
        raw,_=self.archive();offset=raw.index(b'inert-public-byte-marker')
        corrupt=raw[:offset]+b'X'+raw[offset+1:]
        for value in (corrupt,raw[:-30]):
            with self.assertRaises((ContractError,zipfile.BadZipFile,EOFError)):self.decode(value)
    def test_encrypted_flag_refuses(self):
        raw,_=self.archive();changed=bytearray(raw)
        # Set original local and central headers consistently, without decrypting.
        local=raw.index(b'PK\x03\x04');central=raw.index(b'PK\x01\x02')
        for offset in (local+6,central+8):
            flags=struct.unpack_from('<H',changed,offset)[0];struct.pack_into('<H',changed,offset,flags|1)
        with self.assertRaises(ContractError):self.decode(bytes(changed))
