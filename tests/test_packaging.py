"""Regression coverage for release guards, metadata and accidental archive content."""

import importlib.util
import tarfile
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_checks", ROOT / "tools/check_distribution.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class ReleaseGuardTests(unittest.TestCase):
    def metadata(self, extra="", link="https://github.com/sinzbtw/envlatch"):
        return (
            "Metadata-Version: 2.4\nName: envlatch\nVersion: 0.6.1\n"
            "Requires-Python: >=3.10\nLicense-Expression: MIT\nLicense-File: LICENSE\n"
            "Description-Content-Type: text/markdown\n"
            "Project-URL: Repository, https://github.com/sinzbtw/envlatch\n"
            f"{extra}\n# EnvLatch\n[Documentation]({link})\n"
        ).encode()

    def test_release_tag_must_match_and_branches_cannot_publish(self):
        checks.check_tag("0.6.1", "v0.6.1", required=True)
        checks.check_tag("0.6.1", "")
        for tag in ("", "main", "v0.6.0", "0.6.1", "v0.6.1rc1"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                checks.check_tag("0.6.1", tag, required=True)

    def test_metadata_is_valid_and_rejects_runtime_dependencies_or_duplicates(self):
        checks.check_metadata(self.metadata(), "0.6.1")
        for extra in ("Requires-Dist: requests\n", "Name: unrelated\n", "Version: 0.6.0\n"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                checks.check_metadata(self.metadata(extra), "0.6.1")

    def test_description_requires_absolute_links(self):
        with self.assertRaises(ValueError):
            checks.check_metadata(self.metadata(link="README.ru.md"), "0.6.1")

    def test_traversal_and_windows_archive_paths_are_rejected(self):
        for name in ("../.env", "/.env", "src/../../.env", "src\\envlatch\\core.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checks.safe_path(name)

    def test_console_entry_point_must_be_correct(self):
        checks.check_entry_point(b"[console_scripts]\nenvlatch = envlatch.cli:main\n")
        with self.assertRaises(ValueError):
            checks.check_entry_point(b"[console_scripts]\nenvlatch = other:main\n")

    def archives(self, directory, *, wheel_extra=None, tar_extra=None):
        version = "0.6.1"
        prefix = f"envlatch-{version}"
        with zipfile.ZipFile(directory / f"{prefix}-py3-none-any.whl", "w") as archive:
            for source in (ROOT / "src/envlatch").glob("*.py"):
                archive.writestr("envlatch/" + source.name, source.read_bytes())
            archive.writestr(prefix + ".dist-info/METADATA", self.metadata())
            archive.writestr(
                prefix + ".dist-info/entry_points.txt",
                "[console_scripts]\nenvlatch=envlatch.cli:main",
            )
            archive.writestr(
                prefix + ".dist-info/licenses/LICENSE", (ROOT / "LICENSE").read_bytes()
            )
            if wheel_extra:
                archive.writestr(wheel_extra, "private-release-canary")
        with tarfile.open(directory / f"{prefix}.tar.gz", "w:gz") as archive:
            for name in sorted(checks.SOURCE_FILES):
                contents = self.metadata() if name == "PKG-INFO" else b"public test fixture"
                info = tarfile.TarInfo(prefix + "/" + name)
                info.size = len(contents)
                archive.addfile(info, BytesIO(contents))
            for source in [
                *(ROOT / "src/envlatch").glob("*.py"),
                *(ROOT / "tests").glob("test_*.py"),
            ]:
                archive.add(source, arcname=prefix + "/" + source.relative_to(ROOT).as_posix())
            if tar_extra:
                info = tarfile.TarInfo(prefix + "/" + tar_extra)
                info.size = 22
                archive.addfile(info, BytesIO(b"private-release-canary"))

    def test_archive_gate_accepts_clean_content_and_rejects_local_secrets(self):
        for wheel_extra, tar_extra in (
            (None, None),
            ("envlatch/.env", None),
            (None, ".env"),
            (None, "examples/types/local.env"),
        ):
            with self.subTest(wheel_extra=wheel_extra, tar_extra=tar_extra):
                with tempfile.TemporaryDirectory() as temp:
                    directory = Path(temp)
                    self.archives(directory, wheel_extra=wheel_extra, tar_extra=tar_extra)
                    if wheel_extra or tar_extra:
                        with self.assertRaises(ValueError) as caught:
                            checks.check_archives(directory, "0.6.1")
                        self.assertNotIn("private-release-canary", str(caught.exception))
                    else:
                        self.assertEqual(len(checks.check_archives(directory, "0.6.1")), 2)

    def test_stale_artifact_in_dist_directory_blocks_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.archives(directory)
            (directory / "envlatch-0.6.0.tar.gz").write_bytes(b"stale")
            with self.assertRaises(ValueError):
                checks.check_archives(directory, "0.6.1")


if __name__ == "__main__":
    unittest.main()
