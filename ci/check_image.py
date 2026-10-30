#!/usr/bin/env python3
# nwp-core-template: check_image.py 0.1.0
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check a built tool image against the nwp-core image contract.

Usage: check_image.py IMAGE --imports STMT [--fixture-args ARG ...]
                      [--engine docker|podman] [--uid UID]

Static checks read `<engine> image inspect` and need the image to have a
numeric non-root `User`, no Healthcheck, an `Entrypoint` that is not a shell
with `-c`, and a non-empty `org.opencontainers.image.source` label. Run checks
start the image with a read-only root, a `/tmp` tmpfs, no network and a
non-root UID, and each must exit 0 within 300 seconds: `IMAGE --version`,
`python -c STMT` and, with --fixture-args, `IMAGE ARG ...`.

--engine defaults to the NWP_IMAGE_ENGINE environment variable, else docker.
--uid defaults to 54321.

Prints one `PASS <check>` or `FAIL <check>: <reason>` line per check, then
`check_image: <n> passed, <m> failed`.

Exit codes: 0 every check passed, 1 at least one check failed, 2 the engine is
missing, the image cannot be inspected, or a usage error.

Known limits. An engine error in the `rm --force` cleanup after a timeout ends
in a traceback rather than a FAIL line, and an interrupt leaves the container
running. `--uid 0` is accepted. The runs add no `--pull never`, `--cap-drop
ALL` or `--security-opt no-new-privileges`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from typing import NamedTuple

_SOURCE_LABEL = "org.opencontainers.image.source"
_SHELLS = frozenset({"/bin/sh", "sh", "/bin/bash", "bash"})
_USER = re.compile(r"[0-9]+(:[0-9]+)?", re.ASCII)
_INSPECT_TIMEOUT = 60
_RUN_TIMEOUT = 300
_CLEANUP_TIMEOUT = 60


class ImageError(Exception):
    """The engine is missing or the image cannot be inspected."""


class Result(NamedTuple):
    """One check: `reason` is None when it passed."""

    name: str
    reason: str | None


def inspect_config(engine: str, image: str) -> Mapping[str, object]:
    """Return the `.Config` of the image as the engine reports it."""
    if shutil.which(engine) is None:
        raise ImageError(f"engine {engine!r} not found on PATH")
    argv = [engine, "image", "inspect", "--format", "{{json .Config}}", image]
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_INSPECT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ImageError(f"{engine} image inspect: {exc}") from exc
    if proc.returncode != 0:
        detail = " ".join(proc.stderr.split())
        raise ImageError(f"cannot inspect {image!r}: {detail}")
    try:
        config = json.loads(proc.stdout)
    except ValueError as exc:
        raise ImageError(f"{engine} image inspect: invalid JSON") from exc
    if not isinstance(config, dict):
        raise ImageError(f"{engine} image inspect: Config is not an object")
    return config


def _user(config: Mapping[str, object]) -> str | None:
    user = config.get("User")
    if not isinstance(user, str) or not _USER.fullmatch(user):
        return f"User {user!r} is not a numeric UID[:GID]"
    if int(user.partition(":")[0]) == 0:
        return f"User {user!r} is root"
    return None


def _healthcheck(config: Mapping[str, object]) -> str | None:
    healthcheck = config.get("Healthcheck")
    if healthcheck is None:
        return None
    if isinstance(healthcheck, dict) and healthcheck.get("Test") == ["NONE"]:
        return None
    return "a Healthcheck is set; the smoke run replaces it"


def _entrypoint(config: Mapping[str, object]) -> str | None:
    entrypoint = config.get("Entrypoint")
    if not isinstance(entrypoint, list) or not entrypoint:
        return "Entrypoint is empty"
    if entrypoint[0] in _SHELLS and "-c" in entrypoint[1:]:
        return f"Entrypoint is a shell with -c: {entrypoint!r}"
    return None


def _source_label(config: Mapping[str, object]) -> str | None:
    labels = config.get("Labels")
    value = labels.get(_SOURCE_LABEL) if isinstance(labels, dict) else None
    if not isinstance(value, str) or not value:
        return f"label {_SOURCE_LABEL} is missing or empty"
    return None


def static_checks(config: Mapping[str, object]) -> list[Result]:
    """Return the results of the checks that read the image `Config`."""
    return [
        Result("user", _user(config)),
        Result("healthcheck", _healthcheck(config)),
        Result("entrypoint", _entrypoint(config)),
        Result("source-label", _source_label(config)),
    ]


def run_argv(
    engine: str, name: str, uid: int, tail: Sequence[str]
) -> list[str]:
    """Return the argv that runs a container with the contract's limits."""
    return [
        engine,
        "run",
        "--rm",
        "--name",
        name,
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--network",
        "none",
        "--user",
        f"{uid}:{uid}",
        *tail,
    ]


def _run_check(
    check: str, engine: str, uid: int, tail: Sequence[str]
) -> Result:
    name = f"nwp-check-image-{uuid.uuid4().hex[:12]}"
    argv = run_argv(engine, name, uid, tail)
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(
            [engine, "rm", "--force", name],
            check=False,
            capture_output=True,
            timeout=_CLEANUP_TIMEOUT,
        )
        return Result(check, "timeout")
    except OSError as exc:
        return Result(check, f"cannot run {engine}: {exc}")
    if proc.returncode == 0:
        return Result(check, None)
    lines = proc.stderr.strip().splitlines()
    detail = f": {lines[-1][:200]}" if lines else ""
    return Result(check, f"exit {proc.returncode}{detail}")


def run_checks(
    engine: str,
    image: str,
    imports: str,
    fixture_args: Sequence[str],
    uid: int,
) -> list[Result]:
    """Run the smoke runs of the image and return their results."""
    runs = [
        ("version", [image, "--version"]),
        ("imports", ["--entrypoint", "python", image, "-c", imports]),
    ]
    if fixture_args:
        runs.append(("fixture-args", [image, *fixture_args]))
    return [_run_check(check, engine, uid, tail) for check, tail in runs]


def main(argv: list[str] | None = None) -> int:
    """Check the image; return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Check a built image against the nwp-core image contract."
    )
    parser.add_argument("image")
    parser.add_argument("--imports", required=True, metavar="STMT")
    parser.add_argument("--fixture-args", nargs="+", default=[], metavar="ARG")
    parser.add_argument(
        "--engine",
        default=os.environ.get("NWP_IMAGE_ENGINE", "docker"),
        metavar="docker|podman",
    )
    parser.add_argument("--uid", type=int, default=54321)
    args = parser.parse_args(argv)

    try:
        config = inspect_config(args.engine, args.image)
    except ImageError as exc:
        print(f"check_image: {exc}", file=sys.stderr)
        return 2
    results = [
        *static_checks(config),
        *run_checks(
            args.engine,
            args.image,
            args.imports,
            args.fixture_args,
            args.uid,
        ),
    ]
    for result in results:
        if result.reason is None:
            print(f"PASS {result.name}")
        else:
            print(f"FAIL {result.name}: {result.reason}")
    failed = sum(result.reason is not None for result in results)
    print(f"check_image: {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
