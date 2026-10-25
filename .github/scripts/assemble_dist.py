#!/usr/bin/env python3
"""Merge the per-arch ``assets-<arch>.tar`` tarballs of a release into one ``dist/``.

Used by ``../workflows/release.yml``'s ``release-check`` job. Fails when an
arch's tarball is missing, or when two legs produce the same path: a file
name both legs wrote, a file in one leg that is a directory in another (or
the reverse, including a file whose parent directory is another leg's
file), or a symlink/hardlink clashing with any of those. A plain extract
would silently overwrite or half-fail on these.

Usage: assemble_dist.py ARCHES_JSON PARTS_DIR DIST_DIR
"""

from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path, PurePosixPath


class AssembleError(Exception):
    """A tarball is missing or two legs collide on a path."""


def _parents(path: PurePosixPath) -> list[PurePosixPath]:
    return [p for p in path.parents if str(p) != "."]


def _check(arches: list[str], parts: Path) -> list[Path]:
    """Validate every leg without extracting anything; return the tarballs in order."""
    leaves: dict[PurePosixPath, str] = {}  # non-directory entries -> arch
    dirs: dict[PurePosixPath, str] = {}  # directories (explicit or implied) -> arch
    tarballs = []
    for arch in arches:
        tarball = parts / f"assets-{arch}.tar"
        if not tarball.is_file():
            raise AssembleError(f"no release assets uploaded for arch {arch}")
        tarballs.append(tarball)
        with tarfile.open(tarball) as tar:
            for m in tar.getmembers():
                path = PurePosixPath(m.name)
                if str(path) == ".":
                    continue
                if path.is_absolute() or ".." in path.parts:
                    raise AssembleError(f"{m.name} (arch {arch}) escapes dist/")
                implied = _parents(path)
                if m.isdir():
                    implied = [path, *implied]
                for d in implied:
                    if d in leaves and leaves[d] != arch:
                        raise AssembleError(
                            f"dist/{d} is a file for arch {leaves[d]} but a directory for arch "
                            f"{arch}; per-arch file names must include the arch"
                        )
                    dirs.setdefault(d, arch)
                if m.isdir():
                    continue
                other = leaves.get(path) or dirs.get(path)
                if other is not None and other != arch:
                    raise AssembleError(
                        f"dist/{path} is produced by more than one arch leg ({other} and {arch}); "
                        "per-arch file names must include the arch"
                    )
                leaves[path] = arch
    return tarballs


def assemble(arches: list[str], parts: Path, dist: Path) -> None:
    """Extract ``parts/assets-<arch>.tar`` for every arch into ``dist``.

    Every leg is validated first, so a failure leaves ``dist`` untouched.
    """
    arches = list(dict.fromkeys(arches))
    tarballs = _check(arches, parts)
    dist.mkdir(parents=True, exist_ok=True)
    for tarball in tarballs:
        with tarfile.open(tarball) as tar:
            # Paths were checked above and the "data" filter refuses unsafe links.
            tar.extractall(dist, filter="data")


def main(argv: list[str]) -> int:
    """CLI entry point; prints a GitHub ``::error::`` annotation on failure."""
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        assemble(json.loads(argv[1]), Path(argv[2]), Path(argv[3]))
    except (AssembleError, tarfile.TarError, json.JSONDecodeError, OSError) as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
