"""API-diff guard of the public surface."""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

import griffe
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_GIT_TIMEOUT = 60
_SECTION = re.compile(r"## \[([^\]]+)\]")
_BULLET = re.compile(r"[-*+] `([\w.]+)`")


def pick_base(tags: list[str], at_head: set[str]) -> str | None:
    return next((tag for tag in tags if tag not in at_head), None)


def is_releasing(version: str, tags: list[str], at_head: set[str]) -> bool:
    tag = f"v{version}"
    return tag not in tags or tag in at_head


def allowed_breaks(changelog: str, version: str, releasing: bool) -> set[str]:
    wanted = {"Unreleased", version} if releasing else {"Unreleased"}
    allowed: set[str] = set()
    section = subsection = ""
    for line in changelog.splitlines():
        if line.startswith("## "):
            match = _SECTION.match(line)
            section, subsection = (match[1] if match else ""), ""
        elif line.startswith("### "):
            subsection = line[4:].strip()
        elif (
            section in wanted
            and subsection == "Breaking"
            and (bullet := _BULLET.match(line))
        ):
            allowed.add(bullet[1])
    return allowed


def unallowed(
    breakages: Iterable[griffe.Breakage],
    allowed: set[str],
    version: str,
    base: str,
) -> list[str]:
    major = int(version.split(".")[0])
    frozen = major >= 1 and major == int(base.removeprefix("v").split(".")[0])
    return [
        f"{breakage.obj.path}: {breakage.kind.value}"
        for breakage in breakages
        if frozen or breakage.obj.path not in allowed
    ]


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(_ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )
    if proc.returncode != 0:
        detail = " ".join(proc.stderr.split())
        pytest.fail(f"git {args[0]}: {detail}", pytrace=False)
    return proc.stdout


def test_public_surface_matches_the_base_tag() -> None:
    tags = _git("tag", "--list", "v*", "--sort=-v:refname").split()
    at_head = set(_git("tag", "--points-at", "HEAD").split())
    base = pick_base(tags, at_head)
    if base is None:
        pytest.skip(
            "no v* tag visible; API diff skipped until a release tag is fetched"
        )
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        version = str(tomllib.load(handle)["project"]["version"])
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    old = griffe.load_git(
        "cod_nowcast_ons", ref=base, repo=_ROOT, search_paths=["src"]
    )
    new = griffe.load("cod_nowcast_ons", search_paths=[_ROOT / "src"])
    lines = unallowed(
        griffe.find_breaking_changes(old, new),
        allowed_breaks(
            changelog, version, is_releasing(version, tags, at_head)
        ),
        version,
        base,
    )
    assert not lines, (
        f"public surface broke against {base}; see nwp-core's "
        "docs/public-surface-policy.md:\n" + "\n".join(lines)
    )


_TAGS = ["v0.2.0", "v0.1.0"]

_CHANGELOG = """\
# Changelog

## [Unreleased]

### Breaking

- `pkg.f` removed in the next minor.
- Dropped `pkg.nope` mid-sentence.

### Added

- `pkg.h` new helper.

## [0.2.0] - 2026-11-01

### Breaking

- `pkg.g` renamed while releasing.

## [0.1.0] - 2026-10-30

### Breaking

- `pkg.old` removed long ago.
"""

_OLD = "__all__ = ['f', 'ff', 'g']\ndef f(): ...\ndef ff(): ...\ndef g(): ...\n"
_NEW = "__all__ = ['ff', 'g']\ndef ff(): ...\ndef g(): ...\n"


@pytest.fixture
def removed_f() -> Iterator[list[griffe.Breakage]]:
    with (
        griffe.temporary_visited_package("pkg", {"__init__.py": _OLD}) as old,
        griffe.temporary_visited_package("pkg", {"__init__.py": _NEW}) as new,
    ):
        yield list(griffe.find_breaking_changes(old, new))


@pytest.mark.parametrize(
    ("tags", "at_head", "expected"),
    [
        (_TAGS, {"v0.2.0"}, "v0.1.0"),
        (_TAGS, set(), "v0.2.0"),
        ([], set(), None),
    ],
)
def test_pick_base(
    tags: list[str], at_head: set[str], expected: str | None
) -> None:
    assert pick_base(tags, at_head) == expected


@pytest.mark.parametrize(
    ("tags", "at_head", "expected"),
    [
        (["v0.1.0"], set(), True),
        (_TAGS, {"v0.2.0"}, True),
        (_TAGS, set(), False),
    ],
)
def test_is_releasing(
    tags: list[str], at_head: set[str], expected: bool
) -> None:
    assert is_releasing("0.2.0", tags, at_head) is expected


@pytest.mark.parametrize(
    ("releasing", "expected"),
    [(True, {"pkg.f", "pkg.g"}), (False, {"pkg.f"})],
)
def test_allowed_breaks_reads_the_released_section_only_while_releasing(
    releasing: bool, expected: set[str]
) -> None:
    assert allowed_breaks(_CHANGELOG, "0.2.0", releasing) == expected


def test_unallowed_reports_a_break_without_an_allowance(
    removed_f: list[griffe.Breakage],
) -> None:
    assert unallowed(removed_f, set(), "0.2.0", "v0.1.0") == [
        "pkg.f: Public object was removed"
    ]


def test_unallowed_is_empty_when_the_break_is_allowed(
    removed_f: list[griffe.Breakage],
) -> None:
    assert unallowed(removed_f, {"pkg.f"}, "0.2.0", "v0.1.0") == []


def test_unallowed_matches_the_whole_path(
    removed_f: list[griffe.Breakage],
) -> None:
    assert unallowed(removed_f, {"pkg.ff"}, "0.2.0", "v0.1.0") == [
        "pkg.f: Public object was removed"
    ]


def test_unallowed_ignores_allowances_inside_the_base_major(
    removed_f: list[griffe.Breakage],
) -> None:
    assert unallowed(removed_f, {"pkg.f"}, "1.1.0", "v1.0.0") == [
        "pkg.f: Public object was removed"
    ]


def test_unallowed_honours_allowances_across_a_major_bump(
    removed_f: list[griffe.Breakage],
) -> None:
    assert unallowed(removed_f, {"pkg.f"}, "2.0.0", "v1.4.0") == []
