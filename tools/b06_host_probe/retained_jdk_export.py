"""Inspect a local image-save archive and extract only its pinned public JDK tree.

No Docker invocation, networking, container execution, or application-file extraction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile

IMAGE = '554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268'
PREFIX = PurePosixPath('opt/java/openjdk')


def digest_file(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def extract(archive, destination, receipt):
    archive, destination, receipt = map(Path, (archive, destination, receipt))
    destination.mkdir(parents=True, exist_ok=False)
    layers = []
    with tarfile.open(archive) as outer:
        root_name = 'blobs/sha256/' + IMAGE
        root_bytes = outer.extractfile(root_name).read()
        if hashlib.sha256(root_bytes).hexdigest() != IMAGE:
            raise ValueError('pinned-image-manifest-hash-mismatch')
        root = json.loads(root_bytes)
        layer_names = ['blobs/sha256/' + row['digest'].split(':', 1)[1] for row in root['layers']]
        saved = json.load(outer.extractfile('manifest.json'))
        if len(saved) != 1 or saved[0]['Layers'] != layer_names:
            raise ValueError('saved-image-layer-order-mismatch')
        for layer_name in layer_names:
            f = outer.extractfile(layer_name)
            actual = hashlib.file_digest(f, 'sha256').hexdigest()
            if actual != layer_name.rsplit('/', 1)[1]:
                raise ValueError('layer-hash-mismatch')
            layers.append({'sha256': actual, 'bytes': outer.getmember(layer_name).size})
            with tarfile.open(fileobj=outer.extractfile(layer_name), mode='r|*') as layer:
                for item in layer:
                    path = PurePosixPath(item.name)
                    if '..' in path.parts or path.is_absolute():
                        raise ValueError('unsafe-layer-path')
                    if not path.is_relative_to(PREFIX):
                        continue
                    relative = path.relative_to(PREFIX)
                    if any(p.startswith('.wh.') for p in relative.parts):
                        raise ValueError('jdk-whiteout-requires-explicit-review')
                    target = destination.joinpath(*relative.parts)
                    if item.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif item.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.is_symlink():
                            raise ValueError('jdk-symlink-file-overwrite')
                        with layer.extractfile(item) as source, target.open('wb') as output:
                            shutil.copyfileobj(source, output)
                        target.chmod(item.mode & 0o777)
                    elif item.issym():
                        link = PurePosixPath(item.linkname)
                        if link.is_absolute() or not (target.parent / str(link)).resolve().is_relative_to(destination.resolve()):
                            raise ValueError('jdk-link-outside-tree')
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.symlink_to(item.linkname)
                    else:
                        raise ValueError('unsupported-jdk-member-type')
    java = destination / 'bin/java'
    if not java.is_file() or not (destination / 'bin/jlink').is_file():
        raise ValueError('exported-jdk-incomplete')
    files = [{'path': p.relative_to(destination).as_posix(), 'sha256': digest_file(p), 'bytes': p.stat().st_size}
             for p in sorted(destination.rglob('*')) if p.is_file()]
    record = {'schema': 'b06-retained-jdk-export/1', 'image': 'sha256:' + IMAGE,
              'command': 'docker image save --output work/retained-jdk-export-r1/image.tar sha256:' + IMAGE,
              'archive_bytes': archive.stat().st_size, 'archive_sha256': digest_file(archive),
              'layers': layers, 'jdk_prefix': str(PREFIX), 'jdk_release': (destination / 'release').read_text(),
              'jdk_java_sha256': digest_file(java), 'jdk_files': len(files),
              'jdk_manifest_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
              'containers_started': 0, 'model_calls': 0, 'application_runs': 0}
    receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    extract(args.archive, args.destination, args.receipt)
