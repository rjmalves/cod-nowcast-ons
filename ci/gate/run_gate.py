#!/usr/bin/env python3
# nwp-core-template: gate/run_gate.py 0.1.0
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Identifier gate: scan a publication input with a SHA-256 pinned gitleaks.

Usage: run_gate.py --provision
       run_gate.py --mode tree [--repo PATH] [--require-denylist]
       run_gate.py --mode diff [--repo PATH] [--require-denylist]
       run_gate.py --mode history [--repo PATH] [--require-denylist]
       run_gate.py --mode sdist --target PATH [--require-denylist]
       run_gate.py --mode wheel --target PATH [--require-denylist]
       run_gate.py --mode image --target PATH [--base PATH]
                   [--require-denylist]

The script never trusts gitleaks to open, sniff or finish an input. It reads
every committed blob itself, expands zip, gzip and tar layers in memory
(MAX_NESTING levels, MAX_STAGED_BYTES read), classifies each leaf by its bytes
and stages text under synthetic member names in one tar: a leaf longer than
PIECE_BYTES as several pieces that overlap by at least 2 x PIECE_OVERLAP. One
more member lists every path, so path names are scanned too. A leaf that is
neither text nor a readable archive, and bytes of an archive that the script
cannot read, are reported as `FINDING unscannable <path>`.

Every member is a newline, its text, a newline, `#` and a per-run canary. Each
gitleaks invocation must report the canary of every member exactly once, on
the line the script computed, and nothing outside the member's lines: a member
gitleaks dropped or cut without a log line fails the run (exit 2), as does any
gitleaks warning or error line. The `#` keeps an empty assignment at the end
of a leaf (`API_KEY=`) from taking the canary as its value. A piece keeps the
matches that start before PIECE_OVERLAP bytes short of its end, so each has
room to complete. gitleaks matches never overlap, so a match that eats a
delimiter hides the next one, and a piece that starts mid-line sees different
matches than the whole leaf: the first PIECE_OVERLAP bytes of a piece, which
lack their real left context, are therefore also read by the piece before it,
and a match at the leading newline of a piece that starts mid-line is dropped.
Matches that two pieces both find are reported once, on their true line and
column.

The nwp-* identifier rules (gitleaks.toml next to this script, validated at
run time) and the exact denylist (NWP_GATE_DENYLIST, one entry per line) run
from a self-contained config; gitleaks' default secret rules run as a second
invocation. In-repo suppression is disabled and only RuleID, File, StartLine
and StartColumn, and when a report has them EndLine and EndColumn (the base
image exclusion slices the matched text with them; --redact stays on, so the
script never reads a secret), are ever read from a report. The one vendor
suppression left
is the default value allowlists of the second invocation (for example
placeholder values); its default path allowlist only ever sees synthetic
member names.

Memory: MAX_STAGED_BYTES is charged for every committed blob, every payload
read from an archive, every transcoded UTF-16 leaf and ITEM_COST for every
item (path, leaf, piece, zip record, gzip member). The peak Python heap while
classifying and staging is at most 2 x MAX_STAGED_BYTES: what stays alive was
charged, and joining one payload copies at most the bytes charged for it.
Measured with tracemalloc at a 16 MiB limit, input included: 0.8x for UTF-16
text, 1.0x for text, 1.2x for UTF-16 Chinese, 1.1x for a tar.gz past the
limit, 1.4x for a gzip bomb, 1.8x for a gzip or deflated zip payload (the
worst), as proven by test_peak_memory_stays_within_the_bound_in_the_docstring.
The overlap of 2 x PIECE_OVERLAP leaves these figures as they were: a piece
is written to the tar, keeps about 340 bytes (measured) and is charged
ITEM_COST.
Image mode streams each layer and reads one member at a time: every regular
member has its own budget of MAX_STAGED_BYTES, a run budget of
MAX_STAGED_BYTES and MAX_LEAVES is charged for each item that stays alive
across members (the config blob of --base included), and the peak Python
heap is at most 3 x MAX_STAGED_BYTES (at most 2 x for the member being
classified, as above, plus at most 1 x for the items of earlier members),
measured with tracemalloc at a 16 MiB limit by a test of image mode, save
on disk and not counted: 0.6x for 20000 empty members, 1.0x for two large
texts, 1.3x for a binary, 1.7x for a gzip member or a gzip layer, 1.9x for one
large text and 2.0x (the worst) for 4000 small members followed by a large
text. A member larger than MAX_STAGED_BYTES is
never read into memory. IMAGE_MAX_READ_BYTES (4 GiB) caps the decompressed
bytes that image mode reads in all, a skipped member and the rest of a layer
included; past it the run exits 2. The sdist and wheel modes read the target
whole and charge it to MAX_STAGED_BYTES. The strings of a binary are charged
as they are collected.
Not covered by the bound: the memory of the gitleaks process and of its JSON
report (they grow with the number of findings), the parsed form of the JSON
documents of an image save (each is read within MAX_STAGED_BYTES), the `git
ls-tree` output, which is read whole before its paths are charged, and in the
walk modes the output of `git rev-list` (at most MAX_LEAVES + 1 commits), of
one `git diff-tree` (the entries of one commit), of `git rev-list --objects`,
of `git for-each-ref` and of `git cat-file --batch-check`, and the shallow
file.

Known limits. A match longer than PIECE_OVERLAP in a leaf longer than
PIECE_BYTES can be missed, and so can a run of adjacent, overlapping matches
of one rule that is longer than PIECE_OVERLAP after a cut inside a line (the
cut falls inside a line only where the stretch has no newline, and can also
make a false positive). A gitleaks default rule that consumes a delimiter and
carries a value allowlist can hide a neighbouring match the way an allowlisted
nwp-* match once did, because gitleaks drops allowlisted values only after it
has found every match. Git LFS objects are never scanned and Git LFS is
unsupported in repositories that use the gate: a pointer file is staged as the
text it is. Not read: zip extra fields, the gaps between zip entries, the
surplus of a declared size, the slack bytes and numeric fields of a tar
header, and tar header content that tarfile parses and then overwrites (a
repeated pax key, chained extension headers of one kind, a GNU long name or
link together with a pax path or linkpath, and name, prefix, linkname, uname
or gname fields replaced by pax or GNU values: deliberate concealment, which
is out of scope). A tar with non-zero padding or data after its end, a GNU
long name or link or a pax header holding bytes after the content tarfile
parses (a global header included), a GNU sparse member, and a GNU incremental
directory member with NUL bytes are unscannable, and so is a zip with bytes
before its first entry or after its end record, and a zip64 end record that
its locator does not name or that carries extensible data.

Modes. Tree mode scans the blobs of HEAD. History mode scans every commit
reachable from any ref (`git rev-list --all`: branches, tags, remote-tracking
refs, notes, the stash). Diff mode exits 2 when NWP_GATE_HEAD_SHA names no
commit, and otherwise scans the commits of
NWP_GATE_BASE_SHA..NWP_GATE_HEAD_SHA. It runs history mode instead when the
base is forty zeros or names no commit, and that walk covers `--all` plus the
head, so a head that no ref reaches is still scanned. Both walks diff each
commit against its first parent (the empty tree for a root commit, no rename
detection), then stage every added, modified or type-changed blob once, as
`<commit>:<path>` for the first commit in walk order that introduces it, and
add every distinct path of those diffs to the path listing. A deleted blob is
not staged and a gitlink only adds its path. `gitleaks git` is never used: it
would scan patches, not the bytes this script classifies. Each commit's message
is staged as `<commit>:!message` (the bytes after the first blank line of the
commit object). History mode also stages the message of each annotated tag that
a ref under refs/tags/ points at, and of the tags that tag points at in turn,
as `<tag name>:!tag-message`, and every blob that `git rev-list --objects
--all` lists and the walk did not stage as `object:<blob id>`. Only validated
40-hex SHAs, ids that git printed and fixed options are ever passed to git: no
ref name is.

Artifact modes. `--mode sdist|wheel|image --target PATH` scans a built
artifact instead of a repository: --target must be an existing regular file,
and it is exit 2 to give --target to a git mode or --repo to an artifact mode.
The target is sniffed first (`gate: <mode>: unrecognized format`, exit 2): an
sdist must start with the gzip magic, a wheel with `PK\x03\x04` and an image
with `ustar` at offset 257. The target is never passed to gitleaks; the script
stages what it reads, as in the other modes. An sdist or a wheel is read whole,
charged to MAX_STAGED_BYTES and classified at level 0, so its members show as
`<file name>!<member path>`.

An image is a save of `docker save` or `podman save` (docker-archive or OCI
layout; a tar of an image, not a registry or a daemon). Its layers come from
manifest.json, else from index.json through OCI manifests (a nested index is
followed once). Layers are deduplicated and numbered from 01 in the order they
are first seen. A layer is read as a stream by its magic: gzip, zstd (needs
Python 3.14 `compression.zstd`) or an uncompressed tar (see True empty layer
below). Its members show as
`layer-<nn>-<12 hex of the digest>!<path>`, every member's path is listed (a
whiteout too), and the header text of a member (names, owners, link target)
is staged as `!tar-meta`, as in tree mode. The members of the save that are
not layers (manifest, configuration with its `Env`, index) are classified at
level 0 under their save path. The script fails closed (exit 2, naming the
layer digest) for a layer that the manifest lists and the save lacks, a layer
with no members that is not a true empty tar, a zstd layer without
`compression.zstd`, a layer that cannot
be read to its end (a truncated or corrupt gzip or zstd stream included) and a
layer with an unrecognized magic. A save that lists no layer is exit 2 too.

Strings. In the artifact modes only, a binary leaf is staged as
`<display>!strings`: its strings, one per line. A string is a run of at
least STRINGS_MIN (8) characters, each printable ASCII (0x20 to 0x7e or tab)
or well-formed multi-byte UTF-8 that decodes to a character that is not a
control. A binary with no such run stages nothing, and its path is still
listed. A binary that is an unreadable archive stays `FINDING unscannable`.
Tree, diff and history modes still report every binary as unscannable.

Installed packages. In image mode only, a finding is not printed when its
rule is not nwp-denylist, unscannable or plans-path and its member path (the
part after `layer-<nn>-<hex>!` and before any further `!`) has a segment that
is exactly `site-packages` or `dist-packages`; the finding of a listed path is
filtered by that path. The filter runs after the findings are deduplicated and
before any mask is printed, so a filtered finding prints no mask and does not
change the exit code. Image mode always prints
`gate: image: <n> finding(s) under installed packages not reported` before the
summary. Such a finding is otherwise a shape that a dependency ships (a
documentation URL, a sample), not an identifier of the project.

True empty layer. A build step that changes nothing can leave a layer that is
an empty tar, gzipped (BuildKit) or not (`docker save` with the classic image
store). A layer with no members passes only when its decompressed stream is at
least 1,024 bytes, a multiple of 512 bytes, all NUL and read to its end (a gzip
or zstd trailer included); any other layer with no members is exit 2. An
uncompressed layer is recognized by the `ustar` magic or, for an empty tar, by
a first block of NUL bytes.

Base image. `--base PATH`, with image mode only, names a save of the base image
that the target was built from, so that its content is not reported again.
The file must be a tar save, it is never passed to gitleaks, and its bytes
count toward IMAGE_MAX_READ_BYTES. Each save must describe exactly one image
(one manifest.json entry, or one OCI image manifest). A layer's identity is the
SHA-256 of its decompressed tar stream, computed while the script reads it, on
both saves; the digests that a save declares are never trusted. The layers of
the base are read like the target's, with the same fail-closed checks, and not
scanned. They must equal the first k layers of the target in order, with
1 <= k < the target's layer count, else `gate: image: --base is not a base of
the target` (exit 2). A finding whose rule is not nwp-denylist, unscannable or
plans-path is then counted, not printed, when it lies in one of those k layers,
or in a save member that is not a layer and its matched span occurs verbatim in
the config blob of the base. The matched span of a content finding is the text
of the staged member from (StartLine, StartColumn) to (EndLine, EndColumn), so
it holds the key name and the delimiters (`GPG_KEY=<value>`), and a path
finding's span is its listed path. A finding without both end fields, or whose
span cannot be sliced, stays reported. The check runs on the deduplicated
findings, where a finding stands for every match of its rule on its line and is
excluded only if all of them are, before the installed-package filter and the
masks, so each finding is counted once. `gate: image: <n> finding(s) in base
image content not reported` comes before the installed-packages line.

Budgets of image mode. Every regular member is classified with its own
budget of MAX_STAGED_BYTES. A member larger than that is `FINDING
unscannable`, is never read, and its bytes still count toward the read cap
IMAGE_MAX_READ_BYTES. Past that cap, or past MAX_LEAVES items in the run, the
run exits 2.

Shallow clones. Both walks exit 2 when a walked commit with no parents is a
shallow boundary: it is listed in the file that `git rev-parse --git-path
shallow` names (40-hex lines only; no file means not shallow), and its raw
commit object still has a `parent` header. The commits behind such a cut were
never read, so a literal added and removed before it would pass unseen. git
also lists a true root commit in that file when the clone depth equals the
history length; a true root has no `parent` header and is never a boundary, so
a clone that holds the whole walk passes. In diff mode the check applies to the
walk that actually runs, after any fallback to history.

Known limits of the artifact modes. The strings of a binary miss a literal
shorter than STRINGS_MIN characters and a literal that is split by a
character that is not printable (a UTF-16 string in a binary, for example).
The slack bytes of a layer tar (the padding after the end blocks, the bytes
of a member header that tarfile does not parse) are not read. A layer that a
manifest lists twice counts once, so a target that repeats a layer of its base
at its end is not seen as having a proper prefix. A layer that
the manifest of an OCI save lists but that is not a tar, such as an
attestation, is exit 2 when the save has no manifest.json. A save with several
platforms scans the layers of all of them. A layer in zstd needs an interpreter
with `compression.zstd`; on an older one the run exits 2. A layer tar that ends
inside a member header or has no end-of-archive blocks passes, because tarfile
reads the short header as the end; nothing past the cut is in the save.

Known limits of the base check and the filter. The span test is a substring
test on the raw bytes of the base config, so a target literal is excluded when
the base config holds a longer string that contains it (an `s3://` bucket
without its right boundary, a virtual-hosted bucket without its left), and a
JSON-escaped value is compared as escaped. `--base` is trusted: it must be a
save of the pinned public base, because a save of an earlier stage of the
target is also a proper prefix and hides that stage's shape findings. A save
member that is not a layer but is named like a layer's display is counted as
that layer. The installed-packages filter also covers install metadata that
the build writes under site-packages, such as `*.dist-info/direct_url.json`.
A reported nwp-denylist or unscannable finding prints its path even when that
path's own finding was filtered, so the path is not masked.

Known limits of the walks. Diff mode reports a literal that was already in a
file the range touches, not only an added line, because it stages blobs, not
patches. A walk whose items exceed the budget (MAX_STAGED_BYTES, MAX_LEAVES,
and more than MAX_LEAVES commits) fails closed with exit 2. Author and
committer names, e-mail addresses, signatures and ref names are not scanned.
A signed tag's message that a merge commit copies into its `mergetag` header
is not staged (the default merge message copies it into the body, which is
scanned). The entry names of a tree that a ref points at outside any commit are
not path-scanned, although its blobs are staged as `object:<id>`. The message
of an annotated tag that only a ref outside refs/tags/ reaches is not staged.

Environment: NWP_GATE_DENYLIST, NWP_GATE_GITLEAKS (refused when CI is set),
CI, GITHUB_ACTIONS, XDG_CACHE_HOME; diff mode also reads NWP_GATE_BASE_SHA and
NWP_GATE_HEAD_SHA, which must each be 40 lowercase hex digits and are read from
the environment only.

Exit codes: 0 clean, 1 findings, 2 usage or tool error.
"""

from __future__ import annotations

import argparse
import codecs
import collections
import contextlib
import gzip
import hashlib
import http.client
import importlib
import io
import itertools
import json
import lzma
import os
import platform
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import IO, Any, Literal, NamedTuple, cast

GITLEAKS_VERSION = "8.30.1"
GITLEAKS_TARBALL_SHA256 = {
    "linux_x64": (
        "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
    ),
}
# SHA-256 of the `gitleaks` member of the tarball whose SHA-256 is the
# linux_x64 entry of GITLEAKS_TARBALL_SHA256 above.
GITLEAKS_BINARY_SHA256 = {
    "linux_x64": (
        "88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509"
    ),
}
# The smallest --max-archive-depth at which gitleaks reads the members of
# stage.tar (depth 0 reads nothing and exits 0). Staged members are text, so
# gitleaks never opens a second archive layer. Proven by
# test_stage_depth_is_the_smallest_depth_that_finds_a_plant.
STAGE_DEPTH = 1
MAX_NESTING = 3
MAX_STAGED_BYTES = 512 * 1024 * 1024
MAX_LEAVES = 100_000
# Largest piece of a leaf staged as one member. gitleaks 8.30.1 reads a file in
# 100,000-byte chunks (plus a peek of up to 25,000 bytes for a blank line), so
# a member must fit one chunk with its leading newline and canary line (at most
# 49 bytes) or a match cut at a chunk edge is lost without any log line.
# Proven by test_piece_bytes_member_is_read_in_one_chunk.
PIECE_BYTES = 99_000
# Longer than any match a rule produces in practice (a PEM RSA-4096 key block
# is about 3.3 KB). Consecutive pieces overlap by at least 2 x PIECE_OVERLAP
# and a piece keeps only the matches that start before PIECE_OVERLAP bytes
# short of its end: each kept match has at least PIECE_OVERLAP bytes to
# complete, and the first PIECE_OVERLAP bytes of a piece, which lack their real
# left context, are also read by the piece before it. Proven by
# test_pieces_overlap_by_at_least_piece_overlap,
# test_tree_plant_after_a_mid_line_cut_is_found_on_its_true_line,
# test_tree_host_starting_the_line_of_a_piece_start_is_found and
# test_tree_allowlisted_bucket_straddling_a_piece_boundary_is_clean.
PIECE_OVERLAP = 8_192
# Bytes charged to MAX_STAGED_BYTES for every item (path, leaf, piece,
# unscannable mark, zip directory record) on top of its name. Proven by
# test_item_cost_covers_the_measured_memory_per_item.
ITEM_COST = 1_024
# Shortest run of printable characters that the artifact modes take from a
# binary leaf.
STRINGS_MIN = 8
# Image mode's own cap on the decompressed bytes it reads (layer members, save
# members and the bytes that follow a layer's last member), in place of the
# single MAX_STAGED_BYTES read budget of the other modes.
IMAGE_MAX_READ_BYTES = 4 * 1024 * 1024 * 1024

_RELEASE_URL = (
    "https://github.com/gitleaks/gitleaks/releases/download/"
    "v{version}/gitleaks_{version}_{key}.tar.gz"
)
_FINDINGS_EXIT = 99
_NET_TIMEOUT = 60
_GIT_TIMEOUT = 300
_SCAN_TIMEOUT = 1800
_IDENTIFIER_CONFIG = Path(__file__).resolve().with_name("gitleaks.toml")
_SECRET_CONFIG = "[extend]\nuseDefault = true\n"
_CANARY_PREFIX = "nwpgatecanary"
_CANARY_RULE = "nwp-gate-canary"
_RESERVED_RULES = frozenset({"nwp-denylist", _CANARY_RULE})
_TOP_KEYS = frozenset({"title", "rules"})
_RULE_KEYS = frozenset(
    {
        "id",
        "description",
        "regex",
        "secretGroup",
        "entropy",
        "keywords",
        "allowlists",
    }
)
_ALLOWLIST_KEYS = frozenset(
    {"description", "condition", "regexTarget", "regexes", "stopwords"}
)
_LIMIT = "staging limit exceeded"
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")
_ZIP_END = b"PK\x05\x06"
_ZIP_END_SEARCH = (1 << 16) + 22
_ZIP64_LOCATOR = b"PK\x06\x07"
_ZIP64_END = b"PK\x06\x06"
_ZIP_RECORD = 46
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_CONTROL_BYTES = re.compile(rb"[\x00-\x08\x0b\x0e-\x1a\x1c-\x1f]")
_CONTROL_CHARS = re.compile("[\x00-\x1f\x7f]")
_UNPRINTABLE = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_ZEROS = re.compile(rb"\0*")
_PAX_RECORD = re.compile(rb"(\d+) [^=]+=")
_RULE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
_READ = 1 << 20
_GZIP_WINDOW = 4_096
_BLOCK = 512
_EMPTY_TAR = 2 * _BLOCK
_SHA = re.compile(r"[0-9a-f]{40}")
_OID = re.compile(rb"[0-9a-f]{40}")
_NO_SHA = "0" * 40
_DIFF_STATUSES = frozenset({b"A", b"D", b"M", b"T"})
_OBJECT_TYPES = frozenset({b"blob", b"commit", b"tag", b"tree"})
_FILE_TYPES = (0o100000, 0o120000)
_GITLINK_TYPE = 0o160000
_ARTIFACT_MODES = ("sdist", "wheel", "image")
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_OCI_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
_STRING_RUN = re.compile(rb"[\t\x20-\x7e\x80-\xff]{%d,}" % STRINGS_MIN)
# One or more printable characters: ASCII, or a well-formed UTF-8 sequence
# (no overlong form, surrogate or C1 control).
_UTF8_RUN = re.compile(
    rb"(?:[\t\x20-\x7e]+"
    rb"|\xc2[\xa0-\xbf]|[\xc3-\xdf][\x80-\xbf]"
    rb"|\xe0[\xa0-\xbf][\x80-\xbf]|[\xe1-\xec\xee\xef][\x80-\xbf]{2}"
    rb"|\xed[\x80-\x9f][\x80-\xbf]"
    rb"|\xf0[\x90-\xbf][\x80-\xbf]{2}|[\xf1-\xf3][\x80-\xbf]{3}"
    rb"|\xf4[\x80-\x8f][\x80-\xbf]{2})+"
)
_LAYER_MEMBER = re.compile(r"layer-\d{2,}-[0-9a-f]{12}!([^!]*)")
_LINE_SUFFIX = re.compile(r":\d+\Z")
_INSTALLED_DIRS = frozenset({"site-packages", "dist-packages"})
_UNFILTERED_RULES = frozenset({"nwp-denylist", "unscannable", "plans-path"})


def _archive_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [
        OSError,
        EOFError,
        ValueError,
        RuntimeError,
        NotImplementedError,
        struct.error,
        zlib.error,
        lzma.LZMAError,
        gzip.BadGzipFile,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        tarfile.TarError,
    ]
    with contextlib.suppress(ImportError, AttributeError):
        errors.append(importlib.import_module("compression.zstd").ZstdError)
    return tuple(errors)


_ARCHIVE_ERRORS = _archive_errors()
# gitleaks 8.30.1 logs one record per line on stderr: `<time> <LVL> <text>`.
# Observed with --no-color:
#   10:13AM INF scanned ~250 bytes (250 bytes) in 1.05ms
#   10:13AM WRN leaks found: 6
#   10:13AM WRN skipping archive: exceeds max archive depth max_archive_depth=1
#     path=<tar>!m/000001.zip
#   10:13AM INF no leaks found
# A fatal error line still carries ANSI colour codes despite --no-color.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LOG_LINE = re.compile(r"\S+ ([A-Z]{3}) (.*)")
_LEAKS_FOUND = re.compile(r"leaks found: (\d+)")
_QUIET_LEVELS = frozenset({"INF", "DBG", "TRC"})


class GateError(Exception):
    """A usage or tool error, reported on one line with exit code 2."""


class Finding(NamedTuple):
    rule: str
    where: str
    mask: str = ""
    column: int = 0
    base: bool = False


class _Entry(NamedTuple):
    path: str
    kind: bytes
    oid: bytes


class _Want(NamedTuple):
    """An object to read from git, or (without an oid) a path to list."""

    display: str
    oid: bytes = b""
    kind: bytes = b"blob"


class _Change(NamedTuple):
    path: str
    blob: bytes | None


class _Hit(NamedTuple):
    rule: str
    file: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None


class _Item(NamedTuple):
    kind: Literal["path", "text", "unscannable"]
    display: str
    data: bytes = b""


class _Child(NamedTuple):
    display: str
    data: bytes | None


class _Piece(NamedTuple):
    """Where a staged member sits in its leaf (or in the path listing).

    line0 and col0 locate the member's first byte: the leaf line it is on and
    its byte offset inside that line. line_start is true when that byte starts
    a line of the leaf, so the member's synthetic leading newline mirrors a
    real one. end is the (line, column) from which the piece keeps no hit
    (PIECE_OVERLAP bytes before its last byte), in this member's own
    coordinates (gitleaks columns: the byte offset in the line plus 2, or 1
    for the preceding newline), and None for the last piece. canary_line is
    the line the member's canary is on.
    """

    display: str
    line0: int
    col0: int
    line_start: bool
    end: tuple[int, int] | None
    canary_line: int
    listing: bool


class _Staged(NamedTuple):
    members: dict[str, _Piece]
    listing: bytes | bytearray
    unscannable: list[str]


class _Budget:
    """Bytes read and items staged so far, against the staging limits."""

    def __init__(self) -> None:
        self.bytes = MAX_STAGED_BYTES
        self.leaves = MAX_LEAVES

    def take(self, size: int) -> None:
        self.bytes -= size
        if self.bytes < 0:
            raise GateError(_LIMIT)

    def leaf(self) -> None:
        self.leaves -= 1
        if self.leaves < 0:
            raise GateError(_LIMIT)

    def item(self, name: str) -> None:
        self.leaf()
        self.take(len(name.encode("utf-8", "backslashreplace")) + ITEM_COST)


class _Reads:
    """Decompressed bytes image mode has read so far, against its cap."""

    def __init__(self) -> None:
        self.bytes = IMAGE_MAX_READ_BYTES

    def take(self, size: int) -> None:
        self.bytes -= size
        if self.bytes < 0:
            raise GateError("image: read limit exceeded")


def _platform_key() -> str:
    system, machine = platform.system(), platform.machine()
    if (system, machine) == ("Linux", "x86_64"):
        return "linux_x64"
    raise GateError(f"unsupported platform {system}/{machine}")


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _cache_binary() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "nwp-gate" / f"gitleaks-{GITLEAKS_VERSION}" / "gitleaks"


def _download(url: str, dest: Path) -> None:
    try:
        with (
            urllib.request.urlopen(url, timeout=_NET_TIMEOUT) as response,
            dest.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
    except (OSError, http.client.HTTPException) as exc:
        raise GateError(
            f"download failed: {' '.join(str(exc).split())}"
        ) from exc


def _read_verified(path: Path, key: str) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        msg = f"gitleaks binary unreadable: {path} (run --provision)"
        raise GateError(msg) from exc
    if hashlib.sha256(data).hexdigest() != GITLEAKS_BINARY_SHA256[key]:
        raise GateError(f"gitleaks binary checksum mismatch: {path}")
    return data


def provision() -> Path:
    """Download, verify and extract the pinned gitleaks into the cache."""
    key = _platform_key()
    url = _RELEASE_URL.format(version=GITLEAKS_VERSION, key=key)
    dest = _cache_binary()
    with tempfile.TemporaryDirectory(prefix="nwp-gate-") as raw:
        tarball = Path(raw) / "gitleaks.tar.gz"
        _download(url, tarball)
        if _sha256(tarball) != GITLEAKS_TARBALL_SHA256[key]:
            raise GateError("tarball checksum mismatch")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(tarball) as tar:
                member = tar.extractfile("gitleaks")
                if member is None:
                    raise tarfile.ReadError("not a regular file")
                with member:
                    dest.write_bytes(member.read())
            dest.chmod(0o755)
        except (OSError, KeyError, tarfile.TarError) as exc:
            raise GateError(f"cannot extract gitleaks: {exc}") from exc
    _read_verified(dest, key)
    return dest


def _binary_path() -> Path:
    override = os.environ.get("NWP_GATE_GITLEAKS")
    if override and os.environ.get("CI"):
        raise GateError("NWP_GATE_GITLEAKS is refused when CI is set")
    return Path(override) if override else _cache_binary()


def resolve_gitleaks() -> Path:
    """Return the gitleaks binary to scan with, after its SHA-256 check."""
    key = _platform_key()
    binary = _binary_path()
    _read_verified(binary, key)
    return binary


def private_gitleaks(tmp: Path) -> Path:
    """Copy the verified gitleaks bytes into tmp; scans run only that copy."""
    key = _platform_key()
    data = _read_verified(_binary_path(), key)
    copy = tmp / "gitleaks"
    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return copy


def _actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _printable(text: str) -> str:
    return _UNPRINTABLE.sub(lambda m: f"\\u{ord(m[0]):04x}", text)


def _mask(text: str) -> str:
    return f"::add-mask::{text.replace('%', '%25')}"


def load_denylist(require: bool) -> list[str]:
    """Return the NWP_GATE_DENYLIST entries, masking them under Actions."""
    entries = [
        line.strip()
        for line in os.environ.get("NWP_GATE_DENYLIST", "").split("\n")
        if line.strip()
    ]
    if _actions():
        for entry in entries:
            if not _CONTROL_CHARS.search(entry):
                print(_mask(entry), flush=True)
    if require and not entries:
        raise GateError("denylist required but empty")
    for number, entry in enumerate(entries, start=1):
        if "\\E" in entry or "'''" in entry or _CONTROL_CHARS.search(entry):
            raise GateError(
                f"denylist entry {number} contains a forbidden sequence"
            )
    return entries


def _write_private(path: Path, text: str) -> Path:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def validate_config(text: str) -> None:
    """Reject a gate config that could suppress or shadow a rule."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise GateError(f"config: invalid TOML ({exc})") from exc
    for key in data.keys() - _TOP_KEYS:
        raise GateError(f"config: unexpected top-level key '{key}'")
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise GateError("config: rules must be an array of tables")
    seen: set[str] = set()
    for number, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise GateError(f"config: rule {number} is not a table")
        for key in rule.keys() - _RULE_KEYS:
            raise GateError(f"config: rule {number} has unexpected key '{key}'")
        rule_id, regex = rule.get("id"), rule.get("regex")
        if not isinstance(rule_id, str) or not isinstance(regex, str):
            raise GateError(
                f"config: rule {number} needs a string id and regex"
            )
        if not _RULE_ID.fullmatch(rule_id):
            raise GateError(
                f"config: rule {number} id must match [a-z0-9][a-z0-9-]*"
            )
        if rule_id in _RESERVED_RULES:
            raise GateError(f"config: reserved rule id '{rule_id}'")
        if rule_id in seen:
            raise GateError(f"config: repeated rule id '{rule_id}'")
        seen.add(rule_id)
        allowlists = rule.get("allowlists", [])
        if not isinstance(allowlists, list) or not all(
            isinstance(item, dict) for item in allowlists
        ):
            raise GateError(f"config: rule '{rule_id}' allowlists malformed")
        for allowlist in allowlists:
            for key in allowlist.keys() - _ALLOWLIST_KEYS:
                raise GateError(
                    f"config: rule '{rule_id}' allowlist has unexpected "
                    f"key '{key}'"
                )


def load_identifier_config() -> str:
    """Return the committed identifier rules after validating them."""
    try:
        text = _IDENTIFIER_CONFIG.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise GateError(
            f"config: cannot read {_IDENTIFIER_CONFIG.name}"
        ) from exc
    validate_config(text)
    return text


def build_configs(
    tmp: Path, denylist: list[str], canary: str
) -> tuple[Path, Path]:
    """Write the identifier and secret configs; return their paths."""
    identifier = load_identifier_config()
    if denylist:
        alternatives = "|".join(rf"\Q{entry}\E" for entry in denylist)
        identifier += (
            '\n[[rules]]\nid = "nwp-denylist"\n'
            'description = "exact denylist entry"\n'
            f"regex = '''(?i)(?:{alternatives})'''\n"
        )
    canary_rule = (
        f'\n[[rules]]\nid = "{_CANARY_RULE}"\n'
        'description = "scan completeness canary"\n'
        f"regex = '''{re.escape(canary)}'''\n"
    )
    return (
        _write_private(tmp / "identifier.toml", identifier + canary_rule),
        _write_private(tmp / "secret.toml", _SECRET_CONFIG + canary_rule),
    )


def _child_env(*, git: bool = False) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "GITLEAKS_"))
        and key != "NWP_GATE_DENYLIST"
    }
    if git:
        env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def _drain(stream: IO[bytes] | io.BufferedIOBase, budget: _Budget) -> bytes:
    parts = []
    while chunk := stream.read(_READ):
        budget.take(len(chunk))
        parts.append(chunk)
    return b"".join(parts)


def _zip_guard(data: bytes, budget: _Budget) -> None:
    """Charge the central directory zipfile will hold; reject stray bytes.

    zipfile builds one ZipInfo per central-directory record before it yields
    anything, so the records are charged up front (each takes at least 46
    bytes). The end record and its comment must end the blob, and the central
    directory must end where the end record (or the zip64 end record) starts:
    bytes after the end record, and bytes before the first local entry (zipfile
    reads them as a self-extractor stub), are never read. A zip64 locator must
    name the 56-byte zip64 end record right in front of it: zipfile follows the
    locator and skips any extensible data between that record and the locator,
    so a record found by position alone could be a decoy.
    """
    end = data.rfind(_ZIP_END, max(0, len(data) - _ZIP_END_SEARCH))
    if end < 0 or end + 22 > len(data):
        raise zipfile.BadZipFile("no end of central directory record")
    size, offset, comment = struct.unpack_from("<LLH", data, end + 12)
    if end + 22 + comment != len(data):
        raise zipfile.BadZipFile("bytes after the end record")
    location, wide = end, end - 76
    if end >= 20 and data[end - 20 : end - 16] == _ZIP64_LOCATOR:
        if wide < 0 or data[wide : wide + 4] != _ZIP64_END:
            raise zipfile.BadZipFile("zip64 locator names no zip64 end record")
        size, offset = struct.unpack_from("<QQ", data, wide + 40)
        location = wide
    if offset + size != location:
        raise zipfile.BadZipFile("bytes before the central directory")
    if location != end:
        (reloff,) = struct.unpack_from("<Q", data, end - 12)
        (declared,) = struct.unpack_from("<Q", data, wide + 4)
        if reloff != wide or declared != 44:
            raise zipfile.BadZipFile("zip64 locator names no plain end record")
    budget.take(size // _ZIP_RECORD * ITEM_COST)


def _zip_children(
    data: bytes, display: str, budget: _Budget
) -> Iterator[_Child]:
    _zip_guard(data, budget)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.comment:
            yield _Child(f"{display}!zip-comment", archive.comment)
        for info in archive.infolist():
            # zipfile cuts filename at a NUL and, from Python 3.12, replaces it
            # with an Info-ZIP Unicode Path field; orig_filename is the name
            # as stored. Proven by
            # test_classify_zip_member_is_named_by_its_raw_name.
            name = f"{display}!{info.orig_filename}"
            with archive.open(info) as member:
                body = _drain(member, budget)
            yield _Child(name, body if body or not info.is_dir() else None)
            # From Python 3.12 filename can come from a Unicode Path field that
            # the stored name does not show. Proven by
            # test_tree_zip_unicode_path_word_is_found_on_the_zip_name_leaf.
            if info.filename != info.orig_filename.partition("\0")[0]:
                yield _Child(f"{name}!zip-name", info.filename.encode("utf-8"))
            if info.comment:
                yield _Child(f"{name}!zip-comment", info.comment)


def _gzip_fields(data: bytes, start: int) -> list[tuple[str, bytes]]:
    if data[start : start + 2] != b"\x1f\x8b" or len(data) - start < 10:
        raise gzip.BadGzipFile("not a gzip member")
    flags, pos = data[start + 3], start + 10
    fields = []
    if flags & 4:
        (length,) = struct.unpack_from("<H", data, pos)
        fields.append(("gzip-extra", data[pos + 2 : pos + 2 + length]))
        pos += 2 + length
    for bit, label in ((8, "gzip-name"), (16, "gzip-comment")):
        if flags & bit:
            stop = data.find(b"\0", pos)
            if stop < 0:
                raise gzip.BadGzipFile("unterminated header field")
            fields.append((label, data[pos:stop]))
            pos = stop + 1
    return fields


def _gunzip_member(
    data: bytes, start: int, budget: _Budget
) -> tuple[bytes, int]:
    # zlib copies the input it did not use when a member ends, so it is fed a
    # small window at a time: many tiny members then cost a window each, not
    # the rest of the blob each.
    view = memoryview(data)
    inflater = zlib.decompressobj(zlib.MAX_WBITS | 16)
    parts = []
    pos = start
    while not inflater.eof:
        window = view[pos : pos + _GZIP_WINDOW]
        if not window:
            raise EOFError("truncated gzip member")
        out = inflater.decompress(window)
        pos += len(window)
        budget.take(len(out))
        parts.append(out)
    return b"".join(parts), pos - len(inflater.unused_data)


def _gzip_children(
    data: bytes, display: str, budget: _Budget
) -> Iterator[_Child]:
    payload = []
    pos = 0
    while True:
        budget.take(ITEM_COST)
        for label, value in _gzip_fields(data, pos):
            if value:
                yield _Child(f"{display}!{label}", value)
        body, pos = _gunzip_member(data, pos, budget)
        payload.append(body)
        pos = next(_ZEROS.finditer(data, pos)).end()
        if pos == len(data):
            break
        if not data.startswith(b"\x1f\x8b", pos):
            raise gzip.BadGzipFile("data after the gzip stream")
    yield _Child(display, b"".join(payload))


def _tar_size(header: bytes) -> int:
    if header[124] & 0x80:
        raise tarfile.ReadError("base-256 size in an extension header")
    return int(header[124:136].split(b"\0")[0].strip() or b"0", 8)


def _padded(size: int) -> int:
    return -(-size // _BLOCK) * _BLOCK


def _extension_end(data: bytes, kind: bytes, begin: int, end: int) -> int:
    """Where the part of an extension header's data that tarfile parses ends.

    tarfile reads a GNU long name or link up to its first NUL, and pax records
    up to the first byte that does not start a whole record.
    """
    if kind in {tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK}:
        nul = data.find(b"\0", begin, end)
        return end if nul < 0 else nul
    pos = begin
    while record := _PAX_RECORD.match(data, pos, end):
        length = int(record[1])
        if length < 5 or pos + length > end or data[pos + length - 1] != 10:
            break
        pos += length
    return pos


def _check_tar_padding(
    data: bytes, member: tarfile.TarInfo, start: int, after: int
) -> None:
    """Raise unless every byte tarfile skipped around member is zero.

    start is where the previous member ended, not member.offset: a pax global
    header lies between the two, and tarfile leaves it out of member.offset.
    """
    pos, stop = start, member.offset_data - _BLOCK
    while pos < stop:
        header = data[pos : pos + _BLOCK]
        size = _tar_size(header)
        begin = pos + _BLOCK
        pos = begin + _padded(size)
        parsed = _extension_end(data, header[156:157], begin, begin + size)
        if not _ZEROS.fullmatch(data, parsed, pos):
            raise tarfile.ReadError("non-zero bytes in an extension header")
    skipped = member.isreg() or member.type not in tarfile.SUPPORTED_TYPES
    size = member.size if skipped else 0
    if pos != stop or member.sparse is not None:
        raise tarfile.ReadError("unsupported tar header layout")
    used = member.offset_data + size
    if after != member.offset_data + _padded(size) or not _ZEROS.fullmatch(
        data, used, after
    ):
        raise tarfile.ReadError("non-zero padding after member data")


def _tar_meta(member: tarfile.TarInfo, seen: set[str]) -> bytes:
    lines = [member.uname, member.gname]
    if not (member.issym() or member.islnk()):
        lines.append(member.linkname)
    lines += [
        f"{key}={value}"
        for key, value in member.pax_headers.items()
        if key not in {"path", "linkpath"}
    ]
    fresh = [line for line in lines if line and line not in seen]
    seen.update(fresh)
    return "\n".join(fresh).encode("utf-8", "surrogateescape")


def _payload(
    archive: tarfile.TarFile, member: tarfile.TarInfo, budget: _Budget
) -> bytes | None:
    """A link's target text, a regular member's bytes, or None."""
    if member.issym() or member.islnk():
        target = member.linkname.encode("utf-8", "surrogateescape")
        budget.take(len(target))
        return target
    if (stream := archive.extractfile(member)) is None:
        return None
    return _drain(stream, budget)


def _tar_children(
    data: bytes, display: str, budget: _Budget
) -> Iterator[_Child]:
    seen: set[str] = set()
    start = 0
    with tarfile.open(
        fileobj=io.BytesIO(data),
        mode="r:",
        encoding="utf-8",
        errors="surrogateescape",
    ) as archive:
        while (member := archive.next()) is not None:
            name = f"{display}!{member.name}"
            _check_tar_padding(data, member, start, archive.offset)
            start = archive.offset
            yield _Child(name, _payload(archive, member, budget))
            if meta := _tar_meta(member, seen):
                yield _Child(f"{name}!tar-meta", meta)
        # tarfile ends quietly at a corrupt header; only zero padding may follow
        if not _ZEROS.fullmatch(data, archive.offset):
            raise tarfile.ReadError("data after the end of the archive")


def _utf16(data: bytes, budget: _Budget) -> bytes:
    decoder = codecs.getincrementaldecoder("utf-16")()
    parts = []
    for start in range(0, len(data), _READ):
        text = decoder.decode(data[start : start + _READ])
        parts.append(text.encode("utf-8"))
        budget.take(len(parts[-1]))
    decoder.decode(b"", final=True)
    return b"".join(parts)


def _item(
    budget: _Budget,
    kind: Literal["path", "text", "unscannable"],
    display: str,
    data: bytes = b"",
) -> _Item:
    budget.item(display)
    return _Item(kind, display, data)


def _printable_runs(run: bytes) -> Iterator[bytes]:
    if run.isascii():
        yield run
        return
    for part in _UTF8_RUN.finditer(run):
        if len(part[0].decode("utf-8")) >= STRINGS_MIN:
            yield part[0]


def _strings(data: bytes, budget: _Budget) -> bytes:
    """The printable strings of data, one per line, charged as they grow.

    A string is a maximal run of at least STRINGS_MIN characters, each printable
    ASCII (0x20 to 0x7e, or a tab) or a well-formed multi-byte UTF-8 sequence
    that decodes to a non-control character. data is cut into runs of the bytes
    that can be part of one first, so the UTF-8 pattern only sees those.
    """
    out = bytearray()
    for run in _STRING_RUN.finditer(data):
        for text in _printable_runs(run[0]):
            budget.take(len(text) + 1)
            out += text
            out += b"\n"
    return bytes(out)


def _binary(
    data: bytes, display: str, budget: _Budget, strings: bool
) -> Iterator[_Item]:
    if not strings:
        yield _item(budget, "unscannable", display)
    elif text := _strings(data, budget):
        yield _item(budget, "text", f"{display}!strings", text)


def _leaf(
    data: bytes, display: str, budget: _Budget, strings: bool
) -> Iterator[_Item]:
    if data.startswith(_UTF16_BOMS):
        try:
            data = _utf16(data, budget)
        except UnicodeError:
            yield from _binary(data, display, budget, strings)
            return
    if _CONTROL_BYTES.search(data):
        yield from _binary(data, display, budget, strings)
        return
    yield _item(budget, "text", display, data)


def classify(
    data: bytes,
    display: str,
    level: int,
    budget: _Budget,
    *,
    strings: bool = False,
) -> Iterator[_Item]:
    """Yield the text leaves, member paths and unscannable marks of a blob.

    Classification looks at bytes only. level counts the archive layers
    already opened around data; level 0 is a committed blob. With strings, a
    leaf that is neither text nor a readable archive yields its printable
    strings as the text leaf `<display>!strings` (nothing when it has none)
    instead of an unscannable mark.
    """
    opener: Callable[[bytes, str, _Budget], Iterator[_Child]]
    if data.startswith(_ZIP_MAGIC):
        opener = _zip_children
    elif data.startswith(b"\x1f\x8b"):
        opener = _gzip_children
    elif data[257:262] == b"ustar":
        opener = _tar_children
    else:
        yield from _leaf(data, display, budget, strings)
        return
    if level >= MAX_NESTING:
        yield _item(budget, "unscannable", display)
        return
    children = opener(data, display, budget)
    while True:
        try:
            child = next(children, None)
        except _ARCHIVE_ERRORS:
            yield _item(budget, "unscannable", display)
            return
        if child is None:
            return
        if child.display != display:
            yield _item(budget, "path", child.display)
        if child.data is not None:
            yield from classify(
                child.data, child.display, level + 1, budget, strings=strings
            )


def _next_start(data: bytes | bytearray, start: int, stop: int) -> int:
    """Where the piece after data[start:stop] starts.

    The latest line start that leaves at least 2 * PIECE_OVERLAP bytes,
    looking back at most another PIECE_OVERLAP bytes; mid-line when the
    stretch has no newline.
    """
    nominal = stop - 2 * PIECE_OVERLAP
    cut = data.rfind(b"\n", stop - 3 * PIECE_OVERLAP, nominal)
    return cut + 1 if cut >= 0 else nominal


def _pieces(
    data: bytes | bytearray, display: str, listing: bool
) -> Iterator[tuple[bytes | bytearray, _Piece]]:
    start, line, col = 0, 1, 0
    while True:
        stop = min(start + PIECE_BYTES, len(data))
        piece = data[start:stop]
        canary_line = piece.count(b"\n") + 3
        line_start = start == 0 or data[start - 1] == 10
        if stop == len(data):
            yield (
                piece,
                _Piece(
                    display, line, col, line_start, None, canary_line, listing
                ),
            )
            return
        keep = stop - PIECE_OVERLAP
        kept = data.count(b"\n", start, keep)
        if kept:
            kept_start = data.rfind(b"\n", start, keep) + 1
            end = (kept + 1, keep - kept_start + 2)
        else:
            end = (1, keep - start + 2)
        yield (
            piece,
            _Piece(display, line, col, line_start, end, canary_line, listing),
        )
        nxt = _next_start(data, start, stop)
        newlines = data.count(b"\n", start, nxt)
        if newlines:
            next_start = data.rfind(b"\n", start, nxt) + 1
            line, col = line + newlines, nxt - next_start
        else:
            col += nxt - start
        start = nxt


def _stage_leaf(
    tar: tarfile.TarFile,
    members: dict[str, _Piece],
    data: bytes | bytearray,
    where: tuple[str, bool],
    cost: tuple[str, _Budget],
) -> None:
    canary, budget = cost
    for number, (piece, info) in enumerate(_pieces(data, *where)):
        name = f"m/{len(members) + 1:06d}.txt"
        if number:
            budget.item(name)
        body = b"\n" + piece + f"\n#{canary}\n".encode()
        tarinfo = tarfile.TarInfo(name)
        tarinfo.size = len(body)
        tar.addfile(tarinfo, io.BytesIO(body))
        members[name] = info


def stage(
    items: Iterable[_Item], dest: Path, canary: str, budget: _Budget
) -> _Staged:
    """Write the text items and the path listing to a tar at dest.

    Every member is `\n`, a piece of a leaf (the whole leaf up to PIECE_BYTES),
    `\n`, `#`, the canary and `\n`: gitleaks sniffs a file's type only until
    its first newline, and the canary proves that gitleaks read the whole
    member. The `#` keeps an empty assignment at the end of a leaf from
    taking the canary as its value.
    """
    members: dict[str, _Piece] = {}
    listing = bytearray()
    paths = 0
    unscannable: list[str] = []
    with tarfile.open(dest, "w", format=tarfile.USTAR_FORMAT) as tar:
        for item in items:
            if item.kind == "text":
                where = (item.display, False)
                _stage_leaf(tar, members, item.data, where, (canary, budget))
            elif item.kind == "path":
                if paths:
                    listing += b"\n"
                listing += _printable(item.display).encode("utf-8")
                paths += 1
            else:
                unscannable.append(item.display)
        _stage_leaf(tar, members, listing, ("", True), (canary, budget))
    return _Staged(members, listing, unscannable)


def _run_git(
    repo: Path, args: tuple[str, ...], stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            env=_child_env(git=True),
            input=stdin,
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"git {args[0]}: {exc}") from exc


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = _run_git(repo, args, stdin)
    if proc.returncode != 0:
        detail = " ".join(proc.stderr.decode(errors="replace").split())
        raise GateError(f"git {args[0]}: {detail}")
    return proc.stdout


def _head_entries(repo: Path, budget: _Budget) -> list[_Entry]:
    listing = _git(repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries = []
    for record in listing.split(b"\0"):
        if record:
            meta, _, path = record.partition(b"\t")
            _, kind, oid = meta.split(b" ")
            entry = _Entry(path.decode("utf-8", "surrogateescape"), kind, oid)
            budget.item(entry.path)
            entries.append(entry)
    return entries


def _fetch(
    proc: subprocess.Popen[bytes], oid: bytes, kind: bytes, budget: _Budget
) -> bytes:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(oid + b"\n")
    proc.stdin.flush()
    header = proc.stdout.readline().split()
    if len(header) != 3 or header[1] != kind:
        raise GateError("git cat-file: unexpected object")
    size = int(header[2])
    budget.take(size)
    data = proc.stdout.read(size)
    if len(data) != size or proc.stdout.read(1) != b"\n":
        raise GateError("git cat-file: truncated blob")
    return data


def _message(raw: bytes) -> bytes:
    """The bytes after the first blank line of a raw commit or tag object."""
    return raw.partition(b"\n\n")[2]


def _inner_tag(raw: bytes) -> bytes | None:
    """The id of the tag object that a raw tag object points at, if any."""
    head = raw.partition(b"\n\n")[0].split(b"\n")
    if len(head) < 2 or head[1] != b"type tag":
        return None
    oid = head[0].removeprefix(b"object ")
    if oid == head[0] or not _OID.fullmatch(oid):
        raise GateError("git cat-file: malformed tag")
    return oid


@contextlib.contextmanager
def _cat_file(repo: Path, what: str) -> Iterator[subprocess.Popen[bytes]]:
    """Run one `git cat-file --batch`, which must exit 0 once its input ends."""
    command = ["git", "-C", str(repo), "cat-file", "--batch"]
    try:
        with subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_child_env(git=True),
        ) as proc:
            assert proc.stdin is not None
            yield proc
            proc.stdin.close()
            if proc.wait(timeout=_GIT_TIMEOUT) != 0:
                raise GateError("git cat-file: failed")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"cannot {what}: {exc}") from exc


def _read_objects(
    repo: Path, wants: Iterable[_Want], budget: _Budget, what: str
) -> Iterator[_Item]:
    """Yield a path item per path-only want, else the want's classified bytes.

    Blobs are classified as they are; a commit or a tag by its message. A tag
    that points at a tag is followed, under the same display name. One
    `git cat-file --batch` serves every want.
    """
    with _cat_file(repo, f"stage {what}") as proc:
        for want in wants:
            if not want.oid:
                yield _Item("path", want.display)
                continue
            oid = want.oid
            while True:
                data = _fetch(proc, oid, want.kind, budget)
                body = data if want.kind == b"blob" else _message(data)
                yield from classify(body, want.display, 0, budget)
                inner = _inner_tag(data) if want.kind == b"tag" else None
                if inner is None:
                    break
                oid = inner


def _head_items(
    repo: Path, entries: list[_Entry], budget: _Budget
) -> Iterator[_Item]:
    def wants() -> Iterator[_Want]:
        for entry in entries:
            # _head_entries has charged the path
            yield _Want(entry.path)
            if entry.kind == b"blob":
                yield _Want(entry.path, entry.oid)

    return _read_objects(repo, wants(), budget, "tree")


def _gitleaks_command(
    binary: Path,
    tarball: Path,
    config: Path,
    report: Path,
    ignore_dir: Path,
    depth: int,
) -> list[str]:
    return [
        str(binary),
        "dir",
        str(tarball),
        "--config",
        str(config),
        "--ignore-gitleaks-allow",
        "--gitleaks-ignore-path",
        str(ignore_dir),
        "--redact",
        "--no-banner",
        "--no-color",
        "--exit-code",
        str(_FINDINGS_EXIT),
        "--report-format",
        "json",
        "--report-path",
        str(report),
        "--max-archive-depth",
        str(depth),
    ]


def _optional_int(item: Any, key: str) -> int | None:
    value = item.get(key)
    return value if type(value) is int else None


def _read_report(report: Path, name: str) -> list[_Hit]:
    try:
        raw = json.loads(report.read_text(encoding="utf-8"))
        return [
            _Hit(
                item["RuleID"],
                item["File"],
                int(item["StartLine"]),
                int(item["StartColumn"]),
                _optional_int(item, "EndLine"),
                _optional_int(item, "EndColumn"),
            )
            for item in raw
        ]
    except (OSError, ValueError, LookupError, TypeError) as exc:
        raise GateError(f"gitleaks {name} report unreadable") from exc


def _check_log(stderr: str, count: int) -> None:
    """Fail on any gitleaks log line except INF and a matching summary."""
    summaries = []
    for raw in stderr.splitlines():
        line = _ANSI.sub("", raw).strip()
        if not line:
            continue
        record = _LOG_LINE.fullmatch(line)
        if record is None:
            raise GateError("gitleaks logged unrecognized output")
        level, text = record[1], record[2]
        if level in _QUIET_LEVELS:
            continue
        summary = _LEAKS_FOUND.fullmatch(text) if level == "WRN" else None
        if summary is None:
            raise GateError(f"gitleaks logged {level}")
        summaries.append(int(summary[1]))
    if summaries != ([count] if count else []):
        raise GateError("gitleaks leaks-found count differs from its report")


def _invoke(
    binary: Path,
    tmp: Path,
    tarball: Path,
    name: str,
    config: Path,
    depth: int,
) -> list[_Hit]:
    report = tmp / f"{name}.json"
    ignore_dir = tmp / "no-ignore"
    ignore_dir.mkdir(exist_ok=True)
    command = _gitleaks_command(
        binary, tarball, config, report, ignore_dir, depth
    )
    try:
        proc = subprocess.run(
            command,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=_SCAN_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"gitleaks {name} invocation: {exc}") from exc
    if proc.returncode not in {0, _FINDINGS_EXIT}:
        msg = f"gitleaks {name} invocation failed with exit {proc.returncode}"
        raise GateError(msg)
    hits: list[_Hit] = []
    if proc.returncode == _FINDINGS_EXIT:
        hits = _read_report(report, name)
        if not hits:
            raise GateError(f"gitleaks {name} reported leaks but no findings")
    _check_log(proc.stderr.decode("utf-8", "replace"), len(hits))
    return hits


def _verify_canaries(hits: list[_Hit], prefix: str, staged: _Staged) -> None:
    seen: dict[str, list[int]] = {}
    for hit in hits:
        if hit.rule == _CANARY_RULE:
            seen.setdefault(hit.file.removeprefix(prefix), []).append(hit.line)
    unverified = sum(
        seen.get(name) != [piece.canary_line]
        for name, piece in staged.members.items()
    ) + len(seen.keys() - staged.members.keys())
    if unverified:
        raise GateError(
            f"scan incomplete: {unverified} of {len(staged.members)} "
            "staged members unverified"
        )


def _resolve(
    hits: list[_Hit],
    prefix: str,
    staged: _Staged,
    covers: Callable[[_Hit, str, str | None], bool] | None = None,
) -> list[Finding]:
    """Prove every staged member was read, then map hits to display paths.

    A piece keeps the hits that start before PIECE_OVERLAP bytes short of its
    end, so every kept hit has room to complete. The pieces overlap by twice
    that, so the first PIECE_OVERLAP bytes of a piece, which lack their real
    left context, are also read by the piece before it. A hit on a member's own
    canary line is synthetic and dropped, and so is one at the leading newline
    of a piece that starts mid-line. Hits that two pieces both find collapse
    in _dedupe. covers, when given, says whether a hit lies in the content of
    the base image: it gets the hit, the display path (the member's, or the
    listed path) and the listed path of a path finding, and the finding keeps
    the answer in its base flag.
    """
    _verify_canaries(hits, prefix, staged)
    outside = GateError("gitleaks reported a finding outside the stage")
    findings = []
    lines: list[bytes] = []
    for hit in hits:
        piece = staged.members.get(hit.file.removeprefix(prefix))
        if hit.rule == _CANARY_RULE:
            continue
        if piece is None or not 2 <= hit.line <= piece.canary_line:
            raise outside
        row, col = hit.line - 1, hit.column
        if hit.line == piece.canary_line:
            continue
        if not piece.line_start and (row, col) == (1, 1):
            continue
        if piece.end is not None and (row, col) >= piece.end:
            continue
        line = piece.line0 + row - 1
        column = col - 1 + (piece.col0 if row == 1 else 0)
        if not piece.listing:
            base = covers is not None and covers(hit, piece.display, None)
            findings.append(
                Finding(hit.rule, f"{piece.display}:{line}", "", column, base)
            )
            continue
        lines = lines or bytes(staged.listing).split(b"\n")
        if not 1 <= line <= len(lines):
            raise outside
        path = lines[line - 1].decode("utf-8")
        base = covers is not None and covers(hit, path, path)
        findings.append(Finding(hit.rule, f"path:{path}", path, column, base))
    return findings


def run_gitleaks(
    binary: Path,
    tmp: Path,
    tarball: Path,
    configs: tuple[Path, Path],
    staged: _Staged,
    depth: int,
    base: _BaseImage | None = None,
) -> list[Finding]:
    """Run the identifier and secret invocations; return all findings.

    With base, a finding in the content of the base image has its base flag
    set; the spans are sliced from the stage tar, which must still exist.
    """
    findings: list[Finding] = []
    covers = None if base is None else base.checker(tarball)
    for name, config in zip(("identifier", "secret"), configs, strict=True):
        hits = _invoke(binary, tmp, tarball, name, config, depth)
        findings += _resolve(hits, f"{tarball}!", staged, covers)
    return findings


def _dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """One finding per (rule id, where); base content if all of them are."""
    merged: dict[tuple[str, str], Finding] = {}
    for finding in findings:
        key = (finding.rule, finding.where)
        old = merged.get(key)
        if old is not None:
            finding = finding._replace(base=old.base and finding.base)
        merged[key] = finding
    return list(merged.values())


def _scan(
    denylist: list[str],
    source: Callable[[_Budget, list[str]], Iterable[_Item]],
    base: _BaseImage | None = None,
) -> list[Finding]:
    """Stage what source enumerates, scan it and return the findings.

    source gets the budget and a list to append every path it lists to; the
    paths under plans/ become `plans-path` findings. Returns one finding per
    (rule id, display path, line), the key main uses.
    """
    canary = _CANARY_PREFIX + secrets.token_hex(16)
    paths: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nwp-gate-") as raw:
        tmp = Path(raw)
        configs = build_configs(tmp, denylist, canary)
        binary = private_gitleaks(tmp)
        budget = _Budget()
        tarball = tmp / "stage.tar"
        items = source(budget, paths)
        staged = stage(items, tarball, canary, budget)
        found = run_gitleaks(
            binary, tmp, tarball, configs, staged, STAGE_DEPTH, base
        )
    every = [
        *(
            Finding("plans-path", path)
            for path in paths
            if path.startswith("plans/")
        ),
        *(Finding("unscannable", path) for path in staged.unscannable),
        *found,
    ]
    return _dedupe(every)


def scan_tree(repo: Path, denylist: list[str]) -> list[Finding]:
    """Scan the committed blobs of repo's HEAD."""

    def source(budget: _Budget, paths: list[str]) -> Iterable[_Item]:
        entries = _head_entries(repo, budget)
        paths += [entry.path for entry in entries]
        return _head_items(repo, entries, budget)

    return _scan(denylist, source)


def read_sha(name: str) -> str:
    """Return the environment variable name, which must be 40 hex digits."""
    value = os.environ.get(name, "")
    if not _SHA.fullmatch(value):
        raise GateError(f"{name} must be 40 lowercase hex digits")
    return value


def is_commit(repo: Path, sha: str) -> bool:
    """Whether sha names a commit (or a tag that peels to one) in repo."""
    return (
        _run_git(repo, ("cat-file", "-e", f"{sha}^{{commit}}")).returncode == 0
    )


def base_available(repo: Path, base: str) -> bool:
    """Whether base can start a range: not forty zeros, and a known commit."""
    return base != _NO_SHA and is_commit(repo, base)


def _commits(repo: Path, revs: tuple[str, ...]) -> list[tuple[str, str]]:
    """The commits of revs, oldest first, each with its first parent or ''."""
    listing = _git(
        repo,
        "rev-list",
        "--reverse",
        "--topo-order",
        "--parents",
        f"--max-count={MAX_LEAVES + 1}",
        *revs,
    )
    commits = []
    for line in listing.split(b"\n"):
        if line:
            ids = line.split(b" ")
            if not all(_OID.fullmatch(oid) for oid in ids):
                raise GateError("git rev-list: unexpected output")
            parent = ids[1].decode() if len(ids) > 1 else ""
            commits.append((ids[0].decode(), parent))
    if len(commits) > MAX_LEAVES:
        raise GateError(_LIMIT)
    return commits


def _shallow_ids(repo: Path) -> set[bytes]:
    """The ids in the shallow file that git names; none when it has no file."""
    printed = _git(repo, "rev-parse", "--git-path", "shallow")
    path = repo / os.fsdecode(printed.removesuffix(b"\n"))
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return set()
    except OSError as exc:
        raise GateError(f"cannot read the shallow file: {exc}") from exc
    return {line for line in raw.split(b"\n") if _OID.fullmatch(line)}


def _shallow_cut(
    repo: Path, commits: list[tuple[str, str]], budget: _Budget
) -> str | None:
    """The first walked commit that a shallow clone cut off from its parents.

    Such a commit has no parents for git, is listed in the shallow file and
    still has a `parent` header in its raw object. A true root that the file
    lists too (the clone depth equals the history length) has none.
    """
    listed = _shallow_ids(repo)
    roots = [c for c, parent in commits if not parent and c.encode() in listed]
    if not roots:
        return None
    with _cat_file(repo, "read a shallow boundary") as proc:
        for commit in roots:
            raw = _fetch(proc, commit.encode(), b"commit", budget)
            header = raw.partition(b"\n\n")[0].split(b"\n")
            if any(line.startswith(b"parent ") for line in header):
                return commit
    return None


def _parse_diff(raw: bytes) -> list[_Change]:
    """Parse `git diff-tree -r -z --no-renames` output.

    A change names the blob its new side holds, or None when the new side is
    absent or a gitlink.
    """
    fields = raw.split(b"\0")
    if fields.pop() != b"" or len(fields) % 2:
        raise GateError("git diff-tree: unexpected output")
    changes = []
    for meta, path in zip(fields[::2], fields[1::2], strict=True):
        parts = meta.split(b" ")
        if (
            len(parts) != 5
            or not parts[0].startswith(b":")
            or parts[4] not in _DIFF_STATUSES
            or not _OID.fullmatch(parts[3])
        ):
            raise GateError("git diff-tree: unexpected output")
        try:
            file_type = int(parts[1], 8) & 0o170000
        except ValueError as exc:
            raise GateError("git diff-tree: unexpected output") from exc
        if parts[4] == b"D":
            blob = None
        elif file_type in _FILE_TYPES:
            blob = parts[3]
        elif file_type == _GITLINK_TYPE:
            blob = None
        else:
            raise GateError("git diff-tree: unexpected output")
        changes.append(_Change(path.decode("utf-8", "surrogateescape"), blob))
    return changes


def _first_parent_diff(repo: Path, commit: str, parent: str) -> list[_Change]:
    command = ("diff-tree", "-r", "-z", "--no-renames", "--no-commit-id")
    if parent:
        return _parse_diff(_git(repo, *command, parent, commit))
    return _parse_diff(_git(repo, *command, "--root", commit))


def _walk_wants(
    repo: Path,
    commits: list[tuple[str, str]],
    budget: _Budget,
    paths: list[str],
    blobs: set[bytes],
) -> Iterator[_Want]:
    known: set[str] = set()
    for commit, parent in commits:
        yield _Want(f"{commit}:!message", commit.encode(), b"commit")
        for change in _first_parent_diff(repo, commit, parent):
            if change.path not in known:
                known.add(change.path)
                paths.append(change.path)
                budget.item(change.path)
                yield _Want(change.path)
            if change.blob is not None and change.blob not in blobs:
                blobs.add(change.blob)
                yield _Want(f"{commit}:{change.path}", change.blob)


def _tag_wants(repo: Path) -> Iterator[_Want]:
    listing = _git(
        repo,
        "for-each-ref",
        "--format=%(objecttype) %(objectname) %(refname:lstrip=2)",
        "refs/tags/",
    )
    for line in listing.split(b"\n"):
        kind, _, rest = line.partition(b" ")
        oid, _, name = rest.partition(b" ")
        if kind == b"tag":
            if not _OID.fullmatch(oid):
                raise GateError("git for-each-ref: unexpected output")
            shown = _printable(name.decode("utf-8", "surrogateescape"))
            yield _Want(f"{shown}:!tag-message", oid, b"tag")


def _stray_wants(
    repo: Path, revs: tuple[str, ...], blobs: set[bytes]
) -> Iterator[_Want]:
    # --filter drops the trees, but commits and tags stay in the listing
    listing = _git(
        repo,
        "rev-list",
        "--objects",
        *revs,
        "--no-object-names",
        "--filter=object:type=blob",
    )
    typed = _git(
        repo,
        "cat-file",
        "--batch-check=%(objecttype) %(objectname)",
        stdin=listing,
    )
    for line in typed.split(b"\n"):
        kind, _, oid = line.partition(b" ")
        if line and (kind not in _OBJECT_TYPES or not _OID.fullmatch(oid)):
            raise GateError("git cat-file: unexpected output")
        if kind == b"blob" and oid not in blobs:
            blobs.add(oid)
            yield _Want(f"object:{oid.decode()}", oid)


def _scan_walk(
    repo: Path, denylist: list[str], revs: tuple[str, ...], *, history: bool
) -> list[Finding]:
    def source(budget: _Budget, paths: list[str]) -> Iterable[_Item]:
        commits = _commits(repo, revs)
        if history and not commits:
            raise GateError("repository has no commits")
        if cut := _shallow_cut(repo, commits, budget):
            mode = "history" if history else "diff"
            raise GateError(
                f"{mode}: shallow clone cuts the walk at {cut}; "
                "fetch the full history"
            )
        blobs: set[bytes] = set()
        wants: Iterable[_Want] = _walk_wants(
            repo, commits, budget, paths, blobs
        )
        if history:
            wants = itertools.chain(
                wants, _tag_wants(repo), _stray_wants(repo, revs, blobs)
            )
        return _read_objects(
            repo, wants, budget, "history" if history else "range"
        )

    return _scan(denylist, source)


def scan_diff(
    repo: Path, denylist: list[str], base: str, head: str
) -> list[Finding]:
    """Scan every blob and message that the commits of base..head introduce."""
    return _scan_walk(repo, denylist, (f"{base}..{head}",), history=False)


def scan_history(
    repo: Path, denylist: list[str], head: str = ""
) -> list[Finding]:
    """Scan every commit a ref or head reaches, and the stray objects."""
    revs = ("--all", head) if head else ("--all",)
    return _scan_walk(repo, denylist, revs, history=True)


class LayerRef(NamedTuple):
    """A layer of an image save: where it sits and how it is named."""

    member: str
    digest: str
    number: int

    @property
    def display(self) -> str:
        return f"layer-{self.number:02d}-{self.digest[:12]}"


def sniff_target(mode: str, path: Path) -> None:
    """Raise unless path starts like the format that mode reads."""
    try:
        with path.open("rb") as handle:
            head = handle.read(_BLOCK)
    except OSError as exc:
        raise GateError(f"{mode}: cannot read {exc.strerror}") from exc
    known = {
        "sdist": head.startswith(b"\x1f\x8b"),
        "wheel": head.startswith(b"PK\x03\x04"),
        "image": head[257:262] == b"ustar",
    }
    if not known[mode]:
        raise GateError(f"{mode}: unrecognized format")


def _archive_items(target: Path, budget: _Budget) -> Iterator[_Item]:
    try:
        size = target.stat().st_size
        budget.take(size)
        with target.open("rb") as handle:
            data = handle.read(size)
    except OSError as exc:
        raise GateError(f"cannot read the target: {exc.strerror}") from exc
    yield _item(budget, "path", target.name)
    yield from classify(data, target.name, 0, budget, strings=True)


def _read_blob(
    save: tarfile.TarFile,
    index: dict[str, tarfile.TarInfo],
    name: str,
    reads: _Reads,
) -> bytes:
    member = index.get(name)
    stream = None if member is None else save.extractfile(member)
    if member is None or stream is None:
        raise GateError(f"image: {name} is missing from the save")
    if member.size > MAX_STAGED_BYTES:
        raise GateError(f"image: {name} is too large")
    reads.take(member.size)
    return _drain(stream, _Budget())


def _read_json(
    save: tarfile.TarFile,
    index: dict[str, tarfile.TarInfo],
    name: str,
    reads: _Reads,
) -> Any:
    data = _read_blob(save, index, name, reads)
    try:
        return json.loads(data)
    except ValueError as exc:
        raise GateError(f"image: {name} is not valid JSON") from exc


class _Image(NamedTuple):
    """One image of a save: the layers its manifest lists and its config."""

    layers: list[str]
    config: str | None


def _manifest_images(doc: Any) -> list[_Image]:
    if not isinstance(doc, list):
        raise GateError("image: manifest.json is malformed")
    images = []
    for entry in doc:
        layers = entry.get("Layers") if isinstance(entry, dict) else None
        if not isinstance(layers, list) or not all(
            isinstance(name, str) for name in layers
        ):
            raise GateError("image: manifest.json is malformed")
        config = entry.get("Config")
        images.append(
            _Image(layers, config if isinstance(config, str) else None)
        )
    return images


def _blob_ref(descriptor: Any) -> str | None:
    digest = descriptor.get("digest") if isinstance(descriptor, dict) else None
    found = _OCI_DIGEST.fullmatch(digest) if isinstance(digest, str) else None
    return None if found is None else f"blobs/sha256/{found[1]}"


def _blob_name(descriptor: Any) -> str:
    name = _blob_ref(descriptor)
    if name is None:
        raise GateError("image: an OCI descriptor has no sha256 digest")
    return name


def _oci_images(
    read: Callable[[str], Any], doc: Any, depth: int
) -> list[_Image]:
    """The images of an OCI image index, or the one image of a manifest.

    index.json is depth 0; an image index that it names may name more
    manifests (depth 1) but not another index.
    """
    if not isinstance(doc, dict):
        raise GateError("image: an OCI document is malformed")
    if "manifests" in doc:
        if depth > 1:
            raise GateError("image: image index nested more than once")
        listed = doc["manifests"]
        if not isinstance(listed, list):
            raise GateError("image: an OCI document is malformed")
        images: list[_Image] = []
        for descriptor in listed:
            blob = read(_blob_name(descriptor))
            images += _oci_images(read, blob, depth + 1)
        return images
    layers = doc.get("layers")
    if not isinstance(layers, list):
        raise GateError("image: an OCI document is malformed")
    names = [_blob_name(descriptor) for descriptor in layers]
    return [_Image(names, _blob_ref(doc.get("config")))]


def _read_images(
    save: tarfile.TarFile,
    index: dict[str, tarfile.TarInfo],
    reads: _Reads,
) -> list[_Image]:
    def read(name: str) -> Any:
        return _read_json(save, index, name, reads)

    if "manifest.json" in index:
        return _manifest_images(read("manifest.json"))
    if "index.json" in index:
        return _oci_images(read, read("index.json"), 0)
    raise GateError("image: the save has no manifest.json or index.json")


def _single(images: list[_Image], who: str) -> _Image:
    if len(images) != 1:
        raise GateError(
            f"image: the {who} save describes {len(images)} images, not one"
        )
    return images[0]


def _number_layers(images: list[_Image]) -> list[LayerRef]:
    names = [name for image in images for name in image.layers]
    layers = []
    for number, name in enumerate(dict.fromkeys(names), start=1):
        found = _HEX_DIGEST.search(name)
        raw = name.encode("utf-8", "surrogateescape")
        digest = found[0] if found else hashlib.sha256(raw).hexdigest()
        layers.append(LayerRef(name, digest, number))
    if not layers:
        raise GateError("image: the save lists no layers")
    return layers


def resolve_image_layers(
    save: tarfile.TarFile,
    index: dict[str, tarfile.TarInfo],
    reads: _Reads,
) -> list[LayerRef]:
    """The layers of a save, numbered in first-seen order, each once.

    manifest.json names them; when the save has none, index.json does,
    through each OCI manifest it lists.
    """
    return _number_layers(_read_images(save, index, reads))


def _layer_file(
    save: tarfile.TarFile, layer: LayerRef, member: tarfile.TarInfo
) -> IO[bytes]:
    try:
        raw = save.extractfile(member)
    except KeyError as exc:
        raise GateError(f"image: layer {layer.digest} is missing") from exc
    if raw is None:
        raise GateError(f"image: layer {layer.digest} is not a file")
    return raw


def _layer_reader(raw: IO[bytes], layer: LayerRef) -> IO[bytes]:
    head = raw.read(_BLOCK)
    raw.seek(0)
    if head.startswith(b"\x1f\x8b"):
        return cast("IO[bytes]", gzip.GzipFile(fileobj=raw))
    if head.startswith(_ZSTD_MAGIC):
        try:
            zstd = importlib.import_module("compression.zstd")
        except ImportError as exc:
            raise GateError(
                f"image: layer {layer.digest} is zstd and compression.zstd "
                "is unavailable"
            ) from exc
        reader: IO[bytes] = zstd.ZstdFile(raw)
        return reader
    if head[257:262] == b"ustar" or head == bytes(_BLOCK):
        return raw
    raise GateError(f"image: layer {layer.digest} has an unrecognized format")


class _Hashed:
    """A reader that keeps the SHA-256, size and NUL-ness of what it reads."""

    def __init__(self, raw: IO[bytes]) -> None:
        self._raw = raw
        self.sha = hashlib.sha256()
        self.size = 0
        self.zeros = True

    def read(self, size: int = -1) -> bytes:
        chunk = self._raw.read(size)
        self.sha.update(chunk)
        self.size += len(chunk)
        if self.zeros and chunk.count(0) != len(chunk):
            self.zeros = False
        return chunk

    @property
    def empty_tar(self) -> bool:
        """Whether everything read so far is the blocks of an empty tar."""
        return self.zeros and self.size >= _EMPTY_TAR and not self.size % _BLOCK


def _has_data(member: tarfile.TarInfo) -> bool:
    return not (member.issym() or member.islnk()) and (
        member.isreg() or member.type not in tarfile.SUPPORTED_TYPES
    )


def _member_items(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    display: str,
    seen: set[str],
    reads: _Reads,
) -> Iterator[_Item]:
    """One tar member of an image as items, under a budget of its own.

    A member with more than MAX_STAGED_BYTES of data is unscannable and its
    bytes are skipped, not read; they count toward the read cap all the same.
    """
    budget = _Budget()
    yield _item(budget, "path", display)
    has_data = _has_data(member)
    if has_data:
        reads.take(member.size)
    if has_data and member.size > MAX_STAGED_BYTES:
        yield _item(budget, "unscannable", display)
    elif (payload := _payload(archive, member, budget)) is not None:
        yield from classify(payload, display, 0, budget, strings=True)
    if meta := _tar_meta(member, seen):
        name = f"{display}!tar-meta"
        yield _item(budget, "path", name)
        yield from classify(meta, name, 0, budget, strings=True)


def _kept(run: _Budget, items: Iterable[_Item]) -> Iterator[_Item]:
    """Charge what stays alive after an item is staged to the run's budget."""
    for item in items:
        run.item(item.display)
        yield item


def _layer_items(
    save: tarfile.TarFile,
    layer: LayerRef,
    member: tarfile.TarInfo,
    run: _Budget,
    reads: _Reads,
    ids: list[str],
    *,
    scan: bool = True,
) -> Iterator[_Item]:
    """The items of a layer; its identity is appended to ids when it is read.

    The identity is the SHA-256 of the decompressed stream, read to its end.
    Without scan (the layers of a base image) the members are only counted
    and nothing is yielded.
    """
    try:
        with _layer_file(save, layer, member) as raw:
            reader = _Hashed(_layer_reader(raw, layer))
            with tarfile.open(
                fileobj=cast("IO[bytes]", reader),
                mode="r|",
                encoding="utf-8",
                errors="surrogateescape",
            ) as stream:
                seen: set[str] = set()
                count = 0
                for entry in stream:
                    count += 1
                    if not scan:
                        if _has_data(entry):
                            reads.take(entry.size)
                        continue
                    items = _member_items(
                        stream,
                        entry,
                        f"{layer.display}!{entry.name}",
                        seen,
                        reads,
                    )
                    yield from _kept(run, items)
            while chunk := reader.read(_READ):
                reads.take(len(chunk))
            if not count and not reader.empty_tar:
                raise GateError(f"image: layer {layer.digest} has no members")
            ids.append(reader.sha.hexdigest())
    except _ARCHIVE_ERRORS as exc:
        raise GateError(
            f"image: layer {layer.digest} cannot be read ({type(exc).__name__})"
        ) from exc


def _index_save(
    save: tarfile.TarFile, run: _Budget
) -> tuple[list[tarfile.TarInfo], dict[str, tarfile.TarInfo]]:
    members = []
    for entry in save:
        run.item(entry.name)
        members.append(entry)
    return members, {entry.name: entry for entry in members}


def _locate(
    save: tarfile.TarFile,
    index: dict[str, tarfile.TarInfo],
    layers: list[LayerRef],
) -> list[tuple[LayerRef, tarfile.TarInfo]]:
    located = []
    for layer in layers:
        if (found := index.get(layer.member)) is None:
            raise GateError(f"image: layer {layer.digest} is missing")
        _layer_file(save, layer, found).close()
        located.append((layer, found))
    return located


def _span(body: bytes, hit: _Hit) -> bytes | None:
    """The text of a staged member that a hit matched, or None.

    gitleaks counts a line from the newline before it (the first line from
    byte 0): a start column c is byte `newline + c - 1` and an end column,
    which is one past the last byte, is byte `newline + c`. Bytes, not
    characters. None when the hit has no end, or the bounds do not fit body.
    """
    if hit.end_line is None or hit.end_column is None:
        return None
    newlines = [match.start() for match in re.finditer(b"\n", body)]
    if not all(1 <= n <= len(newlines) + 1 for n in (hit.line, hit.end_line)):
        return None
    begin = 0 if hit.line == 1 else newlines[hit.line - 2]
    end = 0 if hit.end_line == 1 else newlines[hit.end_line - 2]
    start, stop = begin + hit.column - 1, end + hit.end_column
    return body[start:stop] if 0 <= start < stop <= len(body) else None


def _staged_body(tarball: Path, name: str) -> bytes | None:
    try:
        with tarfile.open(tarball, "r:") as stage:
            stream = stage.extractfile(name)
            return None if stream is None else stream.read()
    except (OSError, KeyError, tarfile.TarError):
        return None


class _BaseImage:
    """The base image that --base names: layer identities and config blob."""

    def __init__(self, ids: list[str], config: bytes, reads: _Reads) -> None:
        self.ids = ids
        self.config = config
        self.reads = reads
        self.layers: list[str] = []

    def bind(self, displays: list[str], ids: list[str]) -> None:
        """Take the target's layers, or raise unless the base is a prefix."""
        count = len(self.ids)
        if not 1 <= count < len(ids) or ids[:count] != self.ids:
            raise GateError("image: --base is not a base of the target")
        self.layers = [f"{display}!" for display in displays]

    def checker(self, tarball: Path) -> Callable[[_Hit, str, str | None], bool]:
        """Whether a hit lies in the content of the base image.

        A hit in one of the layers of the base does; one in a layer above it
        does not; one anywhere else does when its span occurs in the config
        blob of the base.
        """
        prefix = f"{tarball}!"

        def covers(hit: _Hit, display: str, listed: str | None) -> bool:
            if hit.rule in _UNFILTERED_RULES:
                return False
            for number, layer in enumerate(self.layers):
                if display.startswith(layer):
                    return number < len(self.ids)
            span: bytes | None = None
            if listed is not None:
                span = listed.encode("utf-8")
            elif body := _staged_body(tarball, hit.file.removeprefix(prefix)):
                span = _span(body, hit)
            return span is not None and span != b"" and span in self.config

        return covers


def _read_base(path: Path) -> _BaseImage:
    reads, budget = _Reads(), _Budget()
    ids: list[str] = []
    try:
        with tarfile.open(
            path, "r:", encoding="utf-8", errors="surrogateescape"
        ) as save:
            _, index = _index_save(save, budget)
            image = _single(_read_images(save, index, reads), "base")
            if image.config is None:
                raise GateError("image: the save names no config blob")
            config = _read_blob(save, index, image.config, reads)
            located = _locate(save, index, _number_layers([image]))
            for layer, found in located:
                items = _layer_items(
                    save, layer, found, budget, reads, ids, scan=False
                )
                collections.deque(items, maxlen=0)
    except _ARCHIVE_ERRORS as exc:
        raise GateError(
            f"image: the save cannot be read ({type(exc).__name__})"
        ) from exc
    return _BaseImage(ids, config, reads)


def load_base(path: Path) -> _BaseImage:
    """Read the save --base names: its layer identities and config blob."""
    try:
        sniff_target("image", path)
        return _read_base(path)
    except GateError as exc:
        reason = str(exc).removeprefix("image: ")
        raise GateError(f"image: --base: {reason}") from exc


def _image_items(
    target: Path, run: _Budget, base: _BaseImage | None = None
) -> Iterator[_Item]:
    reads = _Reads() if base is None else base.reads
    if base is not None:
        run.take(len(base.config))
    try:
        with tarfile.open(
            target, "r:", encoding="utf-8", errors="surrogateescape"
        ) as save:
            members, index = _index_save(save, run)
            images = _read_images(save, index, reads)
            if base is not None:
                images = [_single(images, "target")]
            located = _locate(save, index, _number_layers(images))
            ids: list[str] = []
            for layer, found in located:
                yield from _layer_items(save, layer, found, run, reads, ids)
            if base is not None:
                base.bind([layer.display for layer, _ in located], ids)
            layer_ids = {id(found) for _, found in located}
            seen: set[str] = set()
            for entry in members:
                if id(entry) not in layer_ids:
                    items = _member_items(save, entry, entry.name, seen, reads)
                    yield from _kept(run, items)
    except _ARCHIVE_ERRORS as exc:
        raise GateError(
            f"image: the save cannot be read ({type(exc).__name__})"
        ) from exc


def scan_artifact(
    mode: str,
    target: Path,
    denylist: list[str],
    base: _BaseImage | None = None,
) -> list[Finding]:
    """Scan a built sdist, a built wheel or a saved image.

    With base (image mode), a finding in its content has its base flag set.
    """
    sniff_target(mode, target)

    def source(budget: _Budget, paths: list[str]) -> Iterable[_Item]:
        if mode == "image":
            return _image_items(target, budget, base)
        return _archive_items(target, budget)

    return _scan(denylist, source, base)


def _installed(finding: Finding) -> bool:
    """Whether a finding sits under a site-packages or dist-packages path.

    Only a member of a layer has such a path: the part of its display after
    `layer-<nn>-<hex>!` and before any further `!`.
    """
    if finding.rule in _UNFILTERED_RULES:
        return False
    where = finding.where
    if where.startswith("path:"):
        where = where[len("path:") :]
    else:
        where = _LINE_SUFFIX.sub("", where)
    member = _LAYER_MEMBER.match(where)
    return member is not None and not _INSTALLED_DIRS.isdisjoint(
        member[1].split("/")
    )


def _repo_arg(text: str) -> Path:
    path = Path(text)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"{text!r} is not a directory")
    return path


def _target_arg(text: str) -> Path:
    path = Path(text)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"{text!r} is not a regular file")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run the gate; return the process exit code."""
    parser = argparse.ArgumentParser(description="nwp identifier gate runner.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--provision", action="store_true")
    action.add_argument(
        "--mode", choices=["tree", "diff", "history", *_ARTIFACT_MODES]
    )
    parser.add_argument("--repo", type=_repo_arg, metavar="PATH")
    parser.add_argument("--target", type=_target_arg, metavar="PATH")
    parser.add_argument("--base", type=_target_arg, metavar="PATH")
    parser.add_argument("--require-denylist", action="store_true")
    args = parser.parse_args(argv)

    mode: str = args.mode
    artifact = mode in _ARTIFACT_MODES
    if artifact and args.repo is not None:
        parser.error(f"--repo does not apply to {mode} mode")
    if artifact and args.target is None:
        parser.error(f"--target is required for {mode} mode")
    if mode and not artifact and args.target is not None:
        parser.error(f"--target does not apply to {mode} mode")
    if args.base is not None and mode != "image":
        parser.error("--base applies to image mode only")
    repo: Path = Path() if args.repo is None else args.repo
    base = head = ""
    if mode == "diff":
        try:
            base = read_sha("NWP_GATE_BASE_SHA")
            head = read_sha("NWP_GATE_HEAD_SHA")
        except GateError as exc:
            parser.error(str(exc))

    try:
        if args.provision:
            print(provision())
            return 0
        denylist = load_denylist(args.require_denylist)
        if mode == "diff" and not is_commit(repo, head):
            raise GateError("diff: NWP_GATE_HEAD_SHA names no commit")
        if mode == "diff" and not base_available(repo, base):
            print("gate: diff: base unavailable, falling back to history")
            mode = "history"
        if artifact:
            base_image = None if args.base is None else load_base(args.base)
            found = scan_artifact(mode, args.target, denylist, base_image)
        elif mode == "tree":
            found = scan_tree(repo, denylist)
        elif mode == "diff":
            found = scan_diff(repo, denylist, base, head)
        else:
            found = scan_history(repo, denylist, head)
        unique = {(finding.where, finding.rule): finding for finding in found}
    except GateError as exc:
        print(f"gate: {_printable(str(exc))}", file=sys.stderr)
        return 2
    findings = [unique[key] for key in sorted(unique)]
    based = hidden = 0
    if args.base is not None:
        shown = [finding for finding in findings if not finding.base]
        based, findings = len(findings) - len(shown), shown
    if mode == "image":
        shown = [finding for finding in findings if not _installed(finding)]
        hidden, findings = len(findings) - len(shown), shown
    if _actions():
        masks = dict.fromkeys(f.mask for f in findings if f.mask)
        for mask in masks:
            print(_mask(_printable(mask)))
    for finding in findings:
        rule, where = _printable(finding.rule), _printable(finding.where)
        print(f"FINDING {rule} {where}")
    if args.base is not None:
        print(
            f"gate: image: {based} finding(s) in base image content "
            "not reported"
        )
    if mode == "image":
        print(
            f"gate: image: {hidden} finding(s) under installed packages "
            "not reported"
        )
    print(f"gate: {mode}: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
