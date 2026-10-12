import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from tools.b06_host_probe import retained_jdk_export as subject


def fixture(path, extra=None):
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w') as t:
        for name,data in [('opt/java/openjdk/bin/java',b'public-java'),('opt/java/openjdk/bin/jlink',b'public-jlink'),('opt/java/openjdk/release',b'JAVA_VERSION="test"'),('application/untouched',b'not-extracted')]:
            m=tarfile.TarInfo(name);m.size=len(data);m.mode=0o755;t.addfile(m,io.BytesIO(data))
        if extra:
            m=tarfile.TarInfo(extra[0]);m.type=tarfile.SYMTYPE;m.linkname=extra[1];t.addfile(m)
    layer=raw.getvalue();digest=hashlib.sha256(layer).hexdigest()
    root=json.dumps({'layers':[{'digest':'sha256:'+digest}]}).encode();image=hashlib.sha256(root).hexdigest()
    with tarfile.open(path,'w') as t:
        for name,data in [('blobs/sha256/'+image,root),('blobs/sha256/'+digest,layer),('manifest.json',json.dumps([{'Layers':['blobs/sha256/'+digest]}]).encode())]:
            m=tarfile.TarInfo(name);m.size=len(data);t.addfile(m,io.BytesIO(data))
    return image


class RetainedJdkExtractionTests(unittest.TestCase):
    def test_only_pinned_jdk_tree_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);image=fixture(p/'image.tar')
            with patch.object(subject,'IMAGE',image):
                result=subject.extract(p/'image.tar',p/'jdk',p/'receipt.json')
            self.assertEqual(3,result['jdk_files']);self.assertEqual(1,len(result['layers']))
            self.assertFalse((p/'jdk/application').exists());self.assertEqual(0,result['containers_started'])
            with self.assertRaises(FileExistsError):subject.extract(p/'image.tar',p/'jdk',p/'again.json')

    def test_escaping_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);image=fixture(p/'image.tar',('opt/java/openjdk/escape','../../outside'))
            with patch.object(subject,'IMAGE',image),self.assertRaisesRegex(ValueError,'outside-tree'):
                subject.extract(p/'image.tar',p/'jdk',p/'receipt.json')
            self.assertFalse((p/'receipt.json').exists())

    def test_image_pin_is_not_inferred_from_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);fixture(p/'image.tar')
            with self.assertRaises(KeyError):subject.extract(p/'image.tar',p/'jdk',p/'receipt.json')
            self.assertFalse((p/'receipt.json').exists())
