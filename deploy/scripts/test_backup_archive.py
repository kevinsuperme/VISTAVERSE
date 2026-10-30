import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('backup_archive', Path(__file__).with_name('backup_archive.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ArchiveSafetyTests(unittest.TestCase):
    def archive(self, root, name, kind=tarfile.REGTYPE):
        path = Path(root) / 'media.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.linkname = '/outside'
            member.size = 1 if kind == tarfile.REGTYPE else 0
            archive.addfile(member, io.BytesIO(b'x') if member.size else None)
        return path

    def test_rejects_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as root:
            for name, kind in [('../outside', tarfile.REGTYPE), ('/outside', tarfile.REGTYPE),
                               ('a\\b', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                               ('link', tarfile.LNKTYPE), ('device', tarfile.CHRTYPE)]:
                with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                    module.archive_inventory(self.archive(root, name, kind))

    def test_inventory_matches_archive_content(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'source'
            source.mkdir()
            (source / 'image.png').write_bytes(b'x')
            archive = self.archive(root, './image.png')
            self.assertEqual(module.inventory(source), module.archive_inventory(archive))

    def test_rejects_duplicate_member(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'media.tar.gz'
            with tarfile.open(path, 'w:gz') as archive:
                for name in ('x', './x'):
                    member = tarfile.TarInfo(name)
                    archive.addfile(member, io.BytesIO())
            with self.assertRaises(ValueError):
                module.archive_inventory(path)

    @unittest.skipIf(os.name == 'nt', 'Bash fake-CLI checks run under WSL/Linux')
    def test_restore_collision_never_cleans_existing_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.archive(root, 'image.png')
            media = module.archive_inventory(root / 'media.tar.gz')
            (root / 'media-files.json').write_text(json.dumps(media))
            for name in ('postgres.dump', 'metadata.json', 'pg-dump-version.txt'):
                (root / name).write_text('fixture')
            hashes = {}
            for name in ('postgres.dump', 'media.tar.gz', 'metadata.json', 'media-files.json', 'pg-dump-version.txt'):
                with (root / name).open('rb') as stream:
                    hashes[name] = module.digest(stream)
            (root / 'manifest.json').write_text(json.dumps({'format_version': 2,
                'expected_schema_version': 2, 'media_file_count': 1, 'sha256': hashes}))
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            docker = bin_dir / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_CALLS"\nexit 0\n')
            docker.chmod(0o700)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                       DOCKER_CALLS=str(root / 'calls'))
            script = str(Path(__file__).with_name('verify_backup_restore.sh'))
            default = subprocess.run(['bash', script, '--backup-dir', str(root),
                '--compose-project', 'printfilm-restore-test'], env=env, capture_output=True, text=True)
            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertFalse((root / 'calls').exists(), 'default must not invoke Docker')
            self.assertFalse((root / 'restore-report.json').exists())
            module.write_report(root, 'backup-report')
            self.assertTrue(json.loads((root / 'backup-report.json').read_text())['backup_complete'])
            (root / 'restore-report.json').write_text('{"prior_success":true}')
            collision = subprocess.run(['bash', script, '--backup-dir', str(root),
                '--compose-project', 'printfilm-restore-test', '--run'], env=env, capture_output=True, text=True)
            self.assertNotEqual(collision.returncode, 0)
            calls = (root / 'calls').read_text()
            self.assertNotIn('rm ', calls)
            self.assertNotIn('create ', calls)
            self.assertIn('target already exists', collision.stderr)
            self.assertEqual(json.loads((root / 'restore-report.json').read_text()), {'prior_success': True})
            # A failed verification must not replace a previous successful report.
            (root / 'postgres.dump').write_text('tampered')
            prior = (root / 'backup-report.json').read_bytes()
            with self.assertRaises(ValueError):
                module.write_report(root, 'backup-report')
            self.assertEqual((root / 'backup-report.json').read_bytes(), prior)


if __name__ == '__main__':
    unittest.main()
