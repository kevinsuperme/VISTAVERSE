"""Offline release-lock checks: no Docker daemon or production access."""
import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("check_release", Path(__file__).with_name("check_release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_reject_mutable_and_placeholder_tags(self):
        for value in ("latest", "main", "replace-with-release-git-sha", "placeholder", "your-version"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.validate_version(value)

    def test_digest_must_belong_to_selected_repository(self):
        with self.assertRaises(ValueError):
            release.choose_digest("registry/api", {"RepoDigests": ["other/api@sha256:" + "a" * 64]})

    def test_lock_maps_all_images_and_detects_tampering(self):
        def fake_inspect(*args):
            repo = args[-1].rsplit(":", 1)[0]
            return json.dumps([{"Id": "sha256:" + "b" * 64, "RepoDigests": [repo + "@sha256:" + "a" * 64]}])
        with tempfile.TemporaryDirectory() as folder:
            output, record = Path(folder) / "lock.yml", Path(folder) / "record.json"
            with patch.object(release, "run", side_effect=fake_inspect):
                release.create_lock("release-abc", "c" * 40, output, record)
            release.verify_lock(output, record)
            self.assertEqual(len(json.loads(record.read_text())["images"]), 3)
            altered = json.loads(output.read_text())
            altered["services"]["api"]["image"] = "api:latest"
            output.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                release.verify_lock(output, record)

    def test_dirty_local_release_rejected(self):
        with self.assertRaises(ValueError):
            release.create_lock("a" * 40 + "-dirty-20261029", "a" * 40, Path("unused"), Path("unused2"))

    def test_build_metadata_records_dirty_sha_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "build.env"
            with patch.object(release, "run", side_effect=["c" * 40, " M backend/app/main.py"]):
                version = release.build_metadata(output)
            self.assertTrue(version.startswith("c" * 40 + "-dirty-"))
            self.assertIn("PRINTFILM_GIT_DIRTY=true", output.read_text())
            with patch.object(release, "run", side_effect=["c" * 40, ""]), self.assertRaises(FileExistsError):
                release.build_metadata(output)

    def test_unpushed_image_cannot_create_release_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            output, record = Path(folder) / "lock.yml", Path(folder) / "record.json"
            with patch.object(release, "run", return_value=json.dumps([{"Id": "sha256:" + "b" * 64}])), self.assertRaises(ValueError):
                release.create_lock("release-abc", "c" * 40, output, record)
            self.assertFalse(output.exists())
            self.assertFalse(record.exists())

    def test_image_label_revision_mismatch_cannot_create_lock(self):
        info = {"Id": "sha256:" + "b" * 64, "Config": {"Labels": {"org.opencontainers.image.revision": "d" * 40}}}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(release, "run", return_value=json.dumps([info])), self.assertRaises(ValueError):
                release.create_lock("release-abc", "c" * 40, Path(folder) / "lock.yml", Path(folder) / "record.json")


if __name__ == "__main__":
    unittest.main()
