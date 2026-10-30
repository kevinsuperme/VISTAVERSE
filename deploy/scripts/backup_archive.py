"""Safe streaming media inventories. No extraction or link traversal."""
import hashlib
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile
import time


def digest(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1048576), b''):
        h.update(block)
    return h.hexdigest()


def inventory(root):
    root = Path(root)
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            if (Path(base) / name).is_symlink():
                raise ValueError('media symlink rejected')
        for name in files:
            p = Path(base) / name
            if not p.is_file():
                raise ValueError('non-regular media rejected')
            with p.open('rb') as stream:
                result[p.relative_to(root).as_posix()] = {'size': p.stat().st_size, 'sha256': digest(stream)}
    return result


def archive_inventory(path):
    result = {}
    seen = set()
    # Consume through the gzip footer, including padding beyond tar's end marker.
    with gzip.open(path, 'rb') as compressed:
        for _ in iter(lambda: compressed.read(1048576), b''):
            pass
    with tarfile.open(path, 'r|gz') as archive:
        for member in archive:
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or '\\' in member.name:
                raise ValueError('unsafe archive path')
            name = str(p)
            if name in seen:
                raise ValueError('duplicate archive member')
            seen.add(name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError('archive links and special files rejected')
            with archive.extractfile(member) as stream:
                result[name] = {'size': member.size, 'sha256': digest(stream)}
    return result


def verify(root):
    root = Path(root)
    if (root / 'manifest.json').is_symlink():
        raise ValueError('manifest symlink rejected')
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('format_version') != 2:
        raise ValueError('unsupported backup manifest')
    if manifest.get('expected_schema_version') != 2:
        raise ValueError('unsupported schema version')
    for name in ('postgres.dump', 'media.tar.gz', 'metadata.json', 'media-files.json', 'pg-dump-version.txt'):
        p = root / name
        if p.is_symlink() or not p.is_file():
            raise ValueError('invalid backup artifact')
        with p.open('rb') as stream:
            if digest(stream) != manifest['sha256'][name]:
                raise ValueError('backup checksum mismatch: ' + name)
    expected = json.loads((root / 'media-files.json').read_text())
    actual = archive_inventory(root / 'media.tar.gz')
    if expected != actual or manifest['media_file_count'] != len(actual):
        raise ValueError('source/archive inventory mismatch')
    return manifest


def write_report(root, kind, evidence=None):
    """Publish only a completed operation; atomic replace preserves prior success on failure."""
    root = Path(root)
    manifest = verify(root)
    report = {'completed_at_unix': int(time.time()),
              'manifest': {'format_version': manifest['format_version'],
                           'expected_schema_version': manifest['expected_schema_version'],
                           'media_file_count': manifest['media_file_count'],
                           'sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()}}
    if kind == 'backup-report':
        report['backup_complete'] = True
    elif kind == 'restore-report':
        counts = {}
        for line in (Path(evidence) / 'restored-counts.txt').read_text().splitlines():
            name, value = line.split('=', 1)
            counts[name] = int(value)
        if set(counts) != {'users', 'projects', 'task_runs', 'schema_migrations'} or any(v < 0 for v in counts.values()):
            raise ValueError('restored counts missing or invalid')
        report.update(restore_complete=True, schema_version=2, counts=counts,
                      evidence_path=str(Path(evidence).resolve()))
    else:
        raise ValueError('unknown report')
    handle, temp = tempfile.mkstemp(prefix='.' + kind + '-', dir=root)
    try:
        with os.fdopen(handle, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, root / (kind + '.json'))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


if __name__ == '__main__':
    action, target = sys.argv[1:3]
    if action == 'source':
        print(json.dumps(inventory(target), sort_keys=True))
    elif action == 'build':
        root = Path(target)
        hashes = {}
        for name in ('postgres.dump', 'media.tar.gz', 'metadata.json', 'media-files.json', 'pg-dump-version.txt'):
            with (root / name).open('rb') as stream:
                hashes[name] = digest(stream)
        manifest = {'format_version': 2, 'expected_schema_version': 2,
                    'media_file_count': len(json.loads((root / 'media-files.json').read_text())),
                    'sha256': hashes, 'counts_note': 'Restore counts describe the dump snapshot; live counts are not snapshot evidence.'}
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        verify(root)
    elif action == 'verify':
        print(json.dumps(verify(target), sort_keys=True))
    elif action in ('backup-report', 'restore-report'):
        write_report(target, action, sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        raise ValueError('unknown action')
