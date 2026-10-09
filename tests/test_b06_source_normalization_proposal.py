import unittest
from tools.b06_image_artifacts.source_normalization_proposal import normalize_proposed as norm

NAME='org.adempiere.base.source'
def mf(qualifier,host='org.adempiere.base',extra='Import-Package: org.example',host_version=None):
 version='13.0.0.'+qualifier
 return ('Manifest-Version: 1.0\r\nBundle-SymbolicName: '+NAME+'\r\nBundle-Version: '+version+'\r\nEclipse-SourceBundle: '+host+';version="'+(host_version or version)+'";r\r\n oots:="."\r\n'+extra+'\r\n\r\n').encode()
def prop(stamp):return ('#Source Bundle Localization\n#'+stamp+'\nbundleName=Core Source\nbundleVendor=Community\n').encode()

class SourceNormalizationProposalTests(unittest.TestCase):
 def test_exact_timestamp_comment_only(self):
  a=prop('Thu Oct 08 19:43:04 UTC 2026');b=prop('Thu Oct 08 20:01:48 UTC 2026')
  self.assertEqual(norm(NAME,'OSGI-INF/l10n/bundle-src.properties',a),norm(NAME,'OSGI-INF/l10n/bundle-src.properties',b))
  b=b.replace(b'Core Source',b'Changed Resource')
  self.assertNotEqual(norm(NAME,'OSGI-INF/l10n/bundle-src.properties',a),norm(NAME,'OSGI-INF/l10n/bundle-src.properties',b))
 def test_host_qualifier_with_exact_host_base_version_and_roots(self):
  self.assertEqual(norm(NAME,'META-INF/MANIFEST.MF',mf('202610081942')),norm(NAME,'META-INF/MANIFEST.MF',mf('202610082001')))
  for data in (mf('202610081942',host='other'),mf('202610081942',host_version='14.0.0.202610081942'),mf('202610081942').replace(b'oots:="."',b'oots:="elsewhere"')):
   with self.subTest(data=data),self.assertRaises(ValueError):norm(NAME,'META-INF/MANIFEST.MF',data)
 def test_imports_and_other_resources_remain_exact(self):
  a=norm(NAME,'META-INF/MANIFEST.MF',mf('202610081942'))
  b=norm(NAME,'META-INF/MANIFEST.MF',mf('202610082001',extra='Import-Package: wrong'))
  self.assertNotEqual(a,b)
  for entry in ('X.class','config.properties','nested/META-INF/MANIFEST.MF'):
   with self.assertRaises(ValueError):norm(NAME,entry,b'bytes')
 def test_no_name_pattern_or_arbitrary_comment_allowlist(self):
  with self.assertRaises(ValueError):norm('unapproved.source','META-INF/MANIFEST.MF',mf('202610081942'))
  for data in (prop('Wed Oct 08 19:43:04 UTC 2026'),prop('Thu Oct 08 19:43:04 PDT 2026'),b'#arbitrary\n#Thu Oct 08 19:43:04 UTC 2026\nkey=x\n'):
   with self.subTest(data=data),self.assertRaises(ValueError):norm(NAME,'OSGI-INF/l10n/bundle-src.properties',data)
 def test_version_change_not_normalized(self):
  a=norm(NAME,'META-INF/MANIFEST.MF',mf('202610081942'))
  b=norm(NAME,'META-INF/MANIFEST.MF',mf('202610082001').replace(b'13.0.0',b'14.0.0'))
  self.assertNotEqual(a,b)
