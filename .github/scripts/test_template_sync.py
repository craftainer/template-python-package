"""Tests for ``template_sync.py`` and the executable bits CI relies on.

Stdlib ``unittest`` only (see this directory's README); run with
``python3 -m unittest discover -s .github/scripts -p 'test_*.py'`` -- the
``scripts-tests`` prek hook does exactly that.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import template_sync

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_exec(path: Path) -> bool:
    # The mode bits, not os.access(): some bind-mounted filesystems report
    # every file as executable to os.access().
    return bool(path.stat().st_mode & stat.S_IXUSR)


def write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)


class ApplyReplaceExecutableBitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.old, self.new, self.instance = root / "old", root / "new", root / "instance"

    def apply(self, path: str) -> dict[str, list[str]]:
        return template_sync.apply_replace(self.old, self.new, self.instance, {path})

    def test_same_content_gains_executable_bit(self) -> None:
        # The v1.8.0 bug: the template fixed 644 -> 755 with no content change.
        write(self.old / "s.sh", b"#!/bin/sh\n", 0o644)
        write(self.new / "s.sh", b"#!/bin/sh\n", 0o755)
        write(self.instance / "s.sh", b"#!/bin/sh\n", 0o644)
        result = self.apply("s.sh")
        self.assertEqual(result["updated"], ["s.sh"])
        self.assertEqual(stat.S_IMODE((self.instance / "s.sh").stat().st_mode), 0o755)

    def test_same_content_loses_executable_bit(self) -> None:
        write(self.old / "s.sh", b"x\n", 0o755)
        write(self.new / "s.sh", b"x\n", 0o644)
        write(self.instance / "s.sh", b"x\n", 0o755)
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertFalse(is_exec(self.instance / "s.sh"))

    def test_identical_content_and_mode_is_not_reported(self) -> None:
        for root in (self.old, self.new, self.instance):
            write(root / "s.sh", b"x\n", 0o755)
        self.assertEqual(self.apply("s.sh"), {"updated": [], "removed": []})

    def test_changed_content_copies_the_executable_bit(self) -> None:
        write(self.old / "s.sh", b"a\n", 0o644)
        write(self.new / "s.sh", b"b\n", 0o755)
        write(self.instance / "s.sh", b"a\n", 0o644)
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertEqual((self.instance / "s.sh").read_bytes(), b"b\n")
        self.assertTrue(is_exec(self.instance / "s.sh"))

    def test_new_file_keeps_the_executable_bit(self) -> None:
        write(self.new / "s.sh", b"x\n", 0o755)
        self.instance.mkdir()
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertTrue(is_exec(self.instance / "s.sh"))


class DirectlyInvokedScriptsAreExecutableTest(unittest.TestCase):
    """A workflow step that names a script as the command needs mode 755 (exit 126 otherwise)."""

    # Any `.github/scripts/*.sh` mention in a non-comment line that isn't
    # handed to an interpreter (`bash x`, `sh x`, `source x`, `. x`).
    SCRIPT_RE = re.compile(r"(?<![\w.-])((?:\./)?\.github/scripts/[\w.-]+\.sh)\b")
    INTERPRETED_RE = re.compile(
        r"(?:\b(?:bash|sh|source)|(?<!\S)\.)\s+(?:\./)?\.github/scripts/[\w.-]+\.sh"
    )

    def test_every_directly_invoked_script_is_executable(self) -> None:
        invoked: set[str] = set()
        for workflow in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
            for line in workflow.read_text().splitlines():
                if line.lstrip().startswith("#"):
                    continue
                interpreted = {m.group(0).split()[-1] for m in self.INTERPRETED_RE.finditer(line)}
                invoked.update(
                    m.removeprefix("./")
                    for m in self.SCRIPT_RE.findall(line)
                    if m not in interpreted
                )
        self.assertTrue(invoked, "expected the moderate-* workflows to invoke scripts directly")
        for rel in sorted(invoked):
            self.assertTrue(is_exec(REPO_ROOT / rel), f"{rel} is not executable")

    def test_claude_hook_is_executable(self) -> None:
        # .claude/settings.json runs it directly as a hook command.
        self.assertTrue(is_exec(REPO_ROOT / ".claude" / "hooks" / "self-check.sh"))


# An instance that implements `publish-packages` replaces base's default, so
# this class only describes (and can only test) a Makefile that kept it.
_KEPT_DEFAULT = "doesn't implement publish-packages" in (REPO_ROOT / "Makefile").read_text()


@unittest.skipUnless(shutil.which("make"), "make not installed")
@unittest.skipUnless(_KEPT_DEFAULT, "this Makefile implements publish-packages itself")
class DefaultPublishPackagesTest(unittest.TestCase):
    """base's default `publish-packages` fails loudly when a package publish is configured."""

    def run_target(self, **env: str) -> subprocess.CompletedProcess[str]:
        clean = {k: v for k, v in os.environ.items() if not k.endswith("_PUBLISH")}
        return subprocess.run(  # noqa: S603 -- fixed argv, trusted tool
            ["make", "-s", "-C", str(REPO_ROOT), "publish-packages"],  # noqa: S607
            env={**clean, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_no_publish_variable_is_a_noop(self) -> None:
        self.assertEqual(self.run_target().returncode, 0)
        self.assertEqual(self.run_target(NPM_PUBLISH="").returncode, 0)

    def test_any_publish_variable_fails_with_a_clear_message(self) -> None:
        for var in ("PYPI_PUBLISH", "NPM_PUBLISH", "CARGO_PUBLISH"):
            result = self.run_target(**{var: "1"})
            self.assertNotEqual(result.returncode, 0, var)
            self.assertIn(
                f"sets {var} but its Makefile doesn't implement publish-packages", result.stderr
            )


if __name__ == "__main__":
    unittest.main()
