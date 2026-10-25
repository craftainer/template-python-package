"""Tests for ``assemble_dist.py`` and ``has_make_target.sh`` (``release.yml``'s helpers)."""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import assemble_dist

SCRIPTS = Path(__file__).resolve().parent


def make_tar(
    path: Path, entries: dict[str, bytes | None], links: dict[str, str] | None = None
) -> None:
    """Write a tarball: ``name -> bytes`` is a file, ``name -> None`` a directory."""
    with tarfile.open(path, "w") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)


class AssembleDistTest(unittest.TestCase):
    """``assemble`` merges per-arch tarballs and rejects every kind of collision."""

    def setUp(self) -> None:
        """Create empty ``parts/`` and ``dist/`` locations."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.parts = tmp / "parts"
        self.parts.mkdir()
        self.dist = tmp / "dist"

    def leg(self, arch: str, entries: dict[str, bytes | None], **kw: dict[str, str]) -> None:
        """Create ``assets-<arch>.tar``."""
        make_tar(self.parts / f"assets-{arch}.tar", entries, kw.get("links"))

    def assert_collision(self, pattern: str) -> None:
        """Assembling both arches fails with a message matching ``pattern``."""
        with self.assertRaisesRegex(assemble_dist.AssembleError, pattern):
            assemble_dist.assemble(["amd64", "arm64"], self.parts, self.dist)

    def test_merges_disjoint_legs(self) -> None:
        """Different names (and a shared directory) from two legs are all extracted."""
        self.leg("amd64", {"./": None, "./a-amd64.tar": b"1", "./sbom/": None, "./sbom/a": b"x"})
        self.leg("arm64", {"./a-arm64.tar": b"2", "./sbom/": None, "./sbom/b": b"y"})
        assemble_dist.assemble(["amd64", "arm64"], self.parts, self.dist)
        got = sorted(str(p.relative_to(self.dist)) for p in self.dist.rglob("*") if p.is_file())
        self.assertEqual(got, ["a-amd64.tar", "a-arm64.tar", "sbom/a", "sbom/b"])

    def test_empty_leg_is_fine(self) -> None:
        """A leg that produced nothing still assembles."""
        self.leg("amd64", {"./": None})
        assemble_dist.assemble(["amd64"], self.parts, self.dist)
        self.assertTrue(self.dist.is_dir())

    def test_missing_arch(self) -> None:
        """A leg without a tarball is reported by arch."""
        self.leg("amd64", {"./": None})
        self.assert_collision("no release assets uploaded for arch arm64")

    def test_same_file_name(self) -> None:
        """The same file name in two legs is rejected."""
        self.leg("amd64", {"x": b"1"})
        self.leg("arm64", {"./x": b"2"})
        self.assert_collision("more than one arch leg")

    def test_file_then_directory(self) -> None:
        """A file in one leg and a directory of that name in the next is rejected."""
        self.leg("amd64", {"x": b"1"})
        self.leg("arm64", {"x/": None, "x/y": b"2"})
        self.assert_collision("dist/x is a file")

    def test_directory_then_file(self) -> None:
        """A directory in one leg and a file of that name in the next is rejected."""
        self.leg("amd64", {"x/": None, "x/y": b"2"})
        self.leg("arm64", {"x": b"1"})
        self.assert_collision("more than one arch leg")

    def test_file_under_other_legs_file(self) -> None:
        """A file below a path that is another leg's file is rejected (no explicit dir entry)."""
        self.leg("amd64", {"x": b"1"})
        self.leg("arm64", {"x/y": b"2"})
        self.assert_collision("dist/x is a file")

    def test_symlink_clashes(self) -> None:
        """A symlink counts as a file: a dangling link still collides by name."""
        self.leg("amd64", {}, links={"x": "nowhere"})
        self.leg("arm64", {"x": b"1"})
        self.assert_collision("more than one arch leg")

    def test_same_leg_repeat_is_not_a_collision(self) -> None:
        """A path repeated within one leg (or a repeated arch) extracts fine."""
        self.leg("amd64", {"x": b"1"})
        with tarfile.open(self.parts / "assets-amd64.tar", "a") as tar:
            info = tarfile.TarInfo("x")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"2"))
        assemble_dist.assemble(["amd64", "amd64"], self.parts, self.dist)
        self.assertTrue((self.dist / "x").is_file())

    def test_failure_extracts_nothing(self) -> None:
        """A collision in a later leg leaves dist/ empty."""
        self.leg("amd64", {"a": b"1", "x": b"1"})
        self.leg("arm64", {"x": b"2"})
        self.assert_collision("more than one arch leg")
        self.assertFalse(self.dist.exists() and any(self.dist.iterdir()))

    def test_symlink_out_of_dist_is_reported(self) -> None:
        """A link pointing outside dist/ is a reported error, not a traceback."""
        self.leg("amd64", {}, links={"latest": "/etc/passwd"})
        self.assertEqual(assemble_dist.main(["x", '["amd64"]', str(self.parts), str(self.dist)]), 1)

    def test_corrupt_tarball_is_reported(self) -> None:
        """A tarball that is not a tar is a reported error."""
        (self.parts / "assets-amd64.tar").write_bytes(b"not a tar")
        self.assertEqual(assemble_dist.main(["x", '["amd64"]', str(self.parts), str(self.dist)]), 1)

    def test_escaping_path(self) -> None:
        """A member that climbs out of dist/ is rejected."""
        self.leg("amd64", {"../evil": b"1"})
        with self.assertRaisesRegex(assemble_dist.AssembleError, "escapes"):
            assemble_dist.assemble(["amd64"], self.parts, self.dist)


@unittest.skipUnless(shutil.which("make"), "make not installed")
class HasMakeTargetTest(unittest.TestCase):
    """``has_make_target.sh`` tells a defined rule from everything else."""

    def probe(
        self, makefile: str, target: str = "verify-published"
    ) -> subprocess.CompletedProcess[str]:
        """Run the probe in a temp dir containing ``makefile``."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Makefile").write_text(makefile)
            return subprocess.run(  # noqa: S603 -- fixed argv, trusted script
                [str(SCRIPTS / "has_make_target.sh"), target],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_defined_rules(self) -> None:
        """Plain, double-colon, prerequisite-only and recipe-less rules all count."""
        for rule in (
            "verify-published:\n\t@echo hi\n",
            "verify-published::\n\t@echo hi\n",
            "verify-published: other\nother:\n",
            "verify-published:\n",
            ".PHONY: verify-published\nverify-published: ;\n",
            "verify-published: VAR := x\nverify-published:\n\t@true\n",
            'verify-published:\n\t@echo "*** done ***"\n',
        ):
            self.assertEqual(self.probe(rule).returncode, 0, rule)

    def test_recipe_is_not_run(self) -> None:
        """Probing never runs a recipe, `$(MAKE)` lines included."""
        result = self.probe("verify-published:\n\t$(MAKE) boom\nboom:\n\ttouch ran\n")
        self.assertEqual(result.returncode, 0)

    def test_missing_rules(self) -> None:
        """No rule, a mere prerequisite, or a longer name is not the target."""
        for text in (
            "build:\n\t@true\n",
            "build: verify-published\n",
            "verify-published-extra:\n\t@true\n",
            "verify-published: VAR := x\n",
        ):
            self.assertEqual(self.probe(text).returncode, 1, text)

    def test_broken_makefile(self) -> None:
        """A Makefile that fails to parse is an error, not 'missing'."""
        result = self.probe("include does-not-exist.mk\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does-not-exist.mk", result.stdout)


if __name__ == "__main__":
    unittest.main()
