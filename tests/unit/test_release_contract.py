"""The Makefile half of template-base's release contract (>= 1.9.0).

The PyPI upload belongs to `publish-packages`, which runs once in its own job;
the per-arch `publish` must not upload anything.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")


def make(*args: str, publish: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run make in the repo root with PYPI_PUBLISH set to `publish` (or unset)."""
    env = {k: v for k, v in os.environ.items() if k != "PYPI_PUBLISH"}
    if publish is not None:
        env["PYPI_PUBLISH"] = publish
    return subprocess.run(  # noqa: S603 -- fixed argv, trusted tool
        ["make", "-C", str(ROOT), *args],  # noqa: S607
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_publish_packages_is_phony() -> None:
    """a stray file named publish-packages cannot shadow the target."""
    assert re.search(r"^\.PHONY:.*\bpublish-packages\b", (ROOT / "Makefile").read_text(), re.M)


def test_unset_skips_with_a_loud_warning() -> None:
    """without PYPI_PUBLISH the target succeeds and warns."""
    result = make("-s", "publish-packages")
    assert result.returncode == 0
    assert "::warning title=PyPI publish skipped::PYPI_PUBLISH is not set" in result.stdout


@pytest.mark.parametrize(
    ("value", "index"),
    [("pypi", "https://upload.pypi.org/legacy/"), ("testpypi", "https://test.pypi.org/legacy/")],
)
def test_uploads_the_built_files_with_trusted_publishing(value: str, index: str) -> None:
    """the already-built wheel and sdist are uploaded, never rebuilt."""
    result = make("-n", "publish-packages", publish=value)
    assert result.returncode == 0
    assert "publish --trusted-publishing always" in result.stdout
    assert f"--publish-url {index}" in result.stdout
    assert "dist/*.whl dist/*.tar.gz" in result.stdout
    assert "build" not in result.stdout


def test_unknown_value_fails() -> None:
    """a PYPI_PUBLISH value other than pypi/testpypi stops the release."""
    result = make("-s", "publish-packages", publish="1")
    assert result.returncode != 0
    assert "must be 'pypi' or 'testpypi'" in result.stderr


def test_per_arch_publish_uploads_nothing() -> None:
    """the per-arch publish is image-only, so a no-op here."""
    result = make("-n", "publish")
    assert result.returncode == 0
    assert "uv publish" not in result.stdout


def test_verify_published_is_phony() -> None:
    """a stray file named verify-published cannot shadow the target."""
    assert re.search(r"^\.PHONY:.*\bverify-published\b", (ROOT / "Makefile").read_text(), re.M)


def test_verify_published_without_pypi_publish_does_nothing() -> None:
    """with PYPI_PUBLISH unset (another registry publishes) there is nothing to verify."""
    result = make("-s", "verify-published")
    assert result.returncode == 0
    assert "nothing to verify" in result.stdout


def test_verify_published_unknown_value_fails() -> None:
    """a PYPI_PUBLISH value other than pypi/testpypi is rejected before any install."""
    result = make("-s", "verify-published", publish="1")
    assert result.returncode != 0
    assert "must be 'pypi' or 'testpypi'" in result.stderr


def test_release_check_does_not_touch_the_registry() -> None:
    """release-check gates the release, so it only checks the local wheel."""
    text = (ROOT / "scripts" / "release-check.sh").read_text()
    assert "PYPI_PUBLISH" not in text
    assert "pypi.org" not in text
