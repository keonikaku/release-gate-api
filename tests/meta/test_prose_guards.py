"""Meta layer: guards on the prose and on what may be committed.

Two rules, both mechanical, both cheap.

The em dash rule is a house style rule for every published surface. It is a
test rather than a review note because a review note is something a person has
to remember and a test is not.

The credential rule is carried over from the automation repository. Nothing in
this service needs a secret, so the guard exists to keep it that way.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Written as escapes on purpose: the characters themselves must never appear in
# a tracked file, including this one.
EM_DASH = "\u2014"
EN_DASH = "\u2013"

TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".ini", ".json", ".cfg"}

# Assignment of something that looks like a real secret. Matches a quoted value
# of twenty characters or more against a key whose name says what it is.
CREDENTIAL_LITERAL = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|token|private[_-]?key)"
    r"\s*[:=]\s*['\"][^'\"]{20,}['\"]"
)


def tracked_text_files() -> list[Path]:
    """Files git is tracking, filtered to the ones with prose or code in them."""
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        REPO_ROOT / name
        for name in listing.stdout.splitlines()
        if Path(name).suffix in TEXT_SUFFIXES
    ]


TRACKED = tracked_text_files()


def test_there_are_tracked_files_to_check():
    """Git returned a file list. Guards the two checks below.

    Layer: meta
    Covers: none
    Why this layer: a guard over the repository, and an empty list would make
    both of the following pass without reading anything.
    """
    assert len(TRACKED) >= 10


@pytest.mark.parametrize("dash", [EM_DASH, EN_DASH])
def test_no_em_dash_reaches_the_repository(dash):
    """No em dash and no en dash in any tracked file.

    Layer: meta
    Covers: none
    Why this layer: a repository wide grep. It is a build failure rather than a
    style note so that the rule holds without anyone remembering it. Hyphens in
    ranges and in identifiers are unaffected.
    """
    offenders = []
    for path in TRACKED:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if dash in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == [], f"dash {dash!r} found at: {offenders}"


def test_no_credential_literal_is_committed():
    """No file assigns a long literal to something named like a secret.

    Layer: meta
    Covers: none
    Why this layer: it inspects what is committed, which no runtime test can
    see. The service needs no credential, so any match is either a mistake or a
    change of design that should be argued rather than merged quietly.
    """
    offenders = []
    for path in TRACKED:
        if path.name == Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if CREDENTIAL_LITERAL.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == [], f"credential literal at: {offenders}"


def test_the_credential_guard_matches_a_credential():
    """The pattern above catches the thing it is for.

    Layer: meta
    Covers: none
    Why this layer: a guard that has never matched anything is indistinguishable
    from a broken one, so it is proved against a sample rather than trusted.
    """
    sample = 'api_key = "' + "x" * 32 + '"'
    assert CREDENTIAL_LITERAL.search(sample)
    assert not CREDENTIAL_LITERAL.search('api_key = os.environ["API_KEY"]')
