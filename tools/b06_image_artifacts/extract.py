"""Read-only image artifact extraction. No JVM, database, subprocess or network.

This is not a resolved-classpath claim. Duplicate classes retain every origin.
All original artifacts and class bytes remain in the local evidence directory.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024 * 1024
MAX_CLASSES = 1000000
MAX_ARTIFACTS = 50000
MAX_MANIFEST = 256 * 1024 * 1024
LIMITS = {'file_bytes': MAX_FILE, 'unique_blob_bytes': MAX_TOTAL,
          'unique_archive_class_entries': MAX_CLASSES, 'artifact_origins': MAX_ARTIFACTS,
          'manifest_bytes': MAX_MANIFEST}


def check(value, reason):
    if not value:
        raise ValueError(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def collect(roots, jdk, output):
    started = time.monotonic()
    output = Path(output)
    output.mkdir(parents=False, exist_ok=False)
    blobs = output / 'blobs'; blobs.mkdir()
    artifacts, classes, runtime, total = [], [], [], 0
    retained, archives = set(), {}

    def retain(raw):
        nonlocal total
        check(len(raw) <= MAX_FILE, 'artifact-too-large')
        sha = hashlib.sha256(raw).hexdigest(); dest = blobs / sha
        if sha not in retained:
            total += len(raw); check(total <= MAX_TOTAL, 'catalogue-size-bound')
            with dest.open('xb') as stream: stream.write(raw)
            retained.add(sha)
        return sha

    def read(path):
        check(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE,
              'unsafe-or-large-artifact')
        raw = path.read_bytes(); check(len(raw) <= MAX_FILE, 'artifact-grew')
        return raw

    def archive(path, kind):
        raw = read(path); artifact = retain(raw)
        artifacts.append({'path': path.as_posix(), 'kind': kind, 'sha256': artifact, 'bytes': len(raw)})
        check(len(artifacts) <= MAX_ARTIFACTS, 'artifact-origin-count-bound')
        if artifact in archives:
            # Preserve every origin, but decompress/index identical archives only once.
            for row in archives[artifact]: row['artifact_paths'].append(path.as_posix())
            return
        indexed = []; archives[artifact] = indexed
        with zipfile.ZipFile(path) as stream:
            entries = stream.infolist()
            for ordinal, entry in enumerate(entries):
                if entry.is_dir() or not entry.filename.endswith('.class'): continue
                # Read by ZipInfo: duplicate names must not silently select the last copy.
                check(entry.file_size <= MAX_FILE and not entry.flag_bits & 1, 'unsafe-class-entry')
                b = stream.read(entry); sha = hashlib.sha256(b).hexdigest()
                # Exact class bytes remain in the retained original archive. Avoid
                # hundreds of thousands of small files on the Windows bind mount.
                row = {'artifact_paths': [path.as_posix()], 'artifact_sha256': artifact,
                                'entry': entry.filename, 'ordinal': ordinal, 'sha256': sha,
                                'bytes': len(b), 'kind': kind}
                classes.append(row); indexed.append(row)
                check(len(classes) <= MAX_CLASSES, 'class-count-bound')
        check(hashlib.sha256(path.read_bytes()).hexdigest() == artifact, 'artifact-changed-during-read')

    def traversal_error(error):
        raise error

    for root in roots:
        root = Path(root); check(root.is_dir() and not root.is_symlink(), 'artifact-root-missing')
        for directory, dirs, names in os.walk(root, followlinks=False, onerror=traversal_error):
            check(not any((Path(directory)/n).is_symlink() for n in dirs), 'artifact-directory-symlink-unsupported')
            dirs[:] = sorted(dirs)
            for name in sorted(names):
                path = Path(directory)/name
                if path.suffix not in ('.jar', '.class'): continue
                if path.suffix == '.jar': archive(path, 'jar')
                else:
                    raw = read(path); sha = retain(raw)
                    artifacts.append({'path': path.as_posix(), 'kind': 'class-file', 'sha256': sha, 'bytes': len(raw)})
                    check(len(artifacts) <= MAX_ARTIFACTS, 'artifact-origin-count-bound')
                    classes.append({'artifact_paths': [path.as_posix()], 'artifact_sha256': sha,
                                    'entry': None, 'ordinal': None, 'sha256': sha,
                                    'bytes': len(raw), 'kind': 'class-file'})
                    check(len(classes) <= MAX_CLASSES, 'class-count-bound')
    jdk = Path(jdk).resolve(strict=True)
    for relative in ('bin/java', 'release', 'lib/modules'):
        path = jdk/relative; raw = read(path)
        runtime.append({'path': path.as_posix(), 'sha256': retain(raw), 'bytes': len(raw)})
    libraries = sorted((jdk/'lib').rglob('*.so'))
    check(libraries, 'jdk-native-libraries-missing')
    for path in libraries:
        actual = path.resolve(strict=True)
        check(actual.is_relative_to(jdk), 'jdk-library-escaped')
        raw = read(actual)
        runtime.append({'path': path.as_posix(), 'resolved_path': actual.as_posix(),
                        'sha256': retain(raw), 'bytes': len(raw)})
    modules = sorted((jdk/'jmods').glob('*.jmod'))
    check(modules, 'jdk-original-module-classes-missing')
    for path in modules: archive(path, 'jdk-module')
    check(any(v['entry'] == 'classes/java/lang/invoke/InnerClassLambdaMetafactory.class' for v in classes),
          'jdk-generator-classes-missing')
    report = {'schema': 'b06-image-artifact-catalogue/2', 'limits': LIMITS,
              'class_storage': 'original-archive-entry', 'artifacts': artifacts, 'classes': classes,
              'runtime_files': runtime, 'unique_blob_bytes': total,
              'resolved_runtime_claim': False, 'native_admission': False,
              'elapsed_seconds': round(time.monotonic()-started, 6), 'model_calls': 0,
              'native_pairs': 0, 'target_jvm_executions': 0}
    raw = encoded(report)
    check(len(raw) <= MAX_MANIFEST, 'manifest-size-bound')
    with (output/'catalogue.json').open('xb') as stream: stream.write(raw)
    print(json.dumps({'catalogue_sha256': hashlib.sha256(raw).hexdigest(),
                      'artifacts': len(artifacts), 'classes': len(classes),
                      'unique_blob_bytes': total, 'native_admission': False}), flush=True)
    return report


def verify_catalogue(output, report):
    """Offline byte replay: every retained archive entry, duplicate and origin."""
    output = Path(output)
    check(report['schema'] == 'b06-image-artifact-catalogue/2' and report['limits'] == LIMITS,
          'catalogue-version-or-limits')
    check(len(report['classes']) <= MAX_CLASSES and len(report['artifacts']) <= MAX_ARTIFACTS,
          'catalogue-count-bound')
    origins, kinds, sizes = {}, {}, {}
    expected_blobs = set()
    for row in [*report['artifacts'], *report['runtime_files']]:
        h = row['sha256']; check(len(h) == 64 and all(c in '0123456789abcdef' for c in h), 'blob-name')
        if h not in expected_blobs:
            raw = (output/'blobs'/h).read_bytes()
            check(hashlib.sha256(raw).hexdigest() == h and len(raw) == row['bytes'], 'artifact-blob-changed')
        expected_blobs.add(h)
        check(sizes.setdefault(h, row['bytes']) == row['bytes'] and row['bytes'] <= MAX_FILE, 'blob-size-binding')
    check(sum(sizes.values()) == report['unique_blob_bytes'] <= MAX_TOTAL, 'total-blob-bytes')
    check({p.name for p in (output/'blobs').iterdir()} == expected_blobs, 'blob-closure')
    for row in report['artifacts']:
        origins.setdefault(row['sha256'], []).append(row['path'])
        kinds.setdefault(row['sha256'], set()).add(row['kind'])
    check(len({r['path'] for r in report['artifacts']}) == len(report['artifacts']), 'duplicate-artifact-origin')
    grouped = {}
    for row in report['classes']:
        grouped.setdefault(row['artifact_sha256'], []).append(row)
    for h, paths in origins.items():
        rows = grouped.pop(h, [])
        if kinds[h] == {'class-file'}:
            check(sorted(p for r in rows for p in r['artifact_paths']) == sorted(paths), 'loose-class-origins')
            check(all(r['sha256'] == h and r['bytes'] == sizes[h] and r['kind'] == 'class-file' and
                      r['entry'] is None and r['ordinal'] is None for r in rows), 'loose-class-binding')
            continue
        with zipfile.ZipFile(output/'blobs'/h) as archive:
            entries = [(i, e) for i, e in enumerate(archive.infolist())
                       if not e.is_dir() and e.filename.endswith('.class')]
            check(len(entries) == len(rows), 'class-entry-closure')
            for (i, e), row in zip(entries, rows, strict=True):
                check(row['ordinal'] == i and row['entry'] == e.filename and
                      row['kind'] in kinds[h] and
                      sorted(row['artifact_paths']) == sorted(paths), 'class-entry-origin')
                raw = archive.read(e)
                check(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'class-entry-changed')
    check(not grouped, 'unbound-class-artifact')
    return {'artifacts': len(report['artifacts']), 'classes': len(report['classes']),
            'blobs': len(expected_blobs), 'full_class_bytes_replayed': True}


def main():
    check(len(sys.argv) == 1, 'no-input-overrides')
    java = shutil.which('java'); check(java is not None, 'image-java-missing')
    jdk = Path(java).resolve(strict=True).parent.parent
    collect([Path('/application'), Path('/root/.m2')], jdk, Path('/evidence/catalogue'))


if __name__ == '__main__': main()
