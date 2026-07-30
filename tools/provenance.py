"""Who wrote the evidence branch, checked before anything is added to it.

The site says the ledger is written by CI. On a personal repository the platform
cannot express "only this workflow may push here": rulesets refuse to accept the
Actions app as a bypass actor, so a rule that blocked people would block the
publish job too. What the platform does enforce on `gh-pages` is that history
cannot be rewritten or deleted, which means a commit that appears there cannot
later be hidden.

This module closes the rest of the gap the only honest way available. Before the
publish job appends anything, it reads the branch history and fails if any commit
was authored by something other than the Actions bot. A person can still push to
the branch. What they cannot do is push to it and have the next publish carry on
as though nothing happened, or remove the evidence that they did.

The one human commit that exists is the branch creation, and it is allow listed
by SHA rather than by pattern, so the exception cannot widen.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MACHINE_AUTHOR = "41898282+github-actions[bot]@users.noreply.github.com"

# The commit that created the branch, made by hand before the first publish job
# existed. Pinned by SHA: a second human commit is not covered by this and will
# fail the check.
BOOTSTRAP_COMMITS = frozenset({"661f15c11c88ff4c9d41f2c8b25968bee5c88372"})


@dataclass(frozen=True)
class Commit:
    """One commit on the evidence branch."""

    sha: str
    author_email: str
    subject: str

    @property
    def machine_written(self) -> bool:
        return self.author_email == MACHINE_AUTHOR

    @property
    def allowed(self) -> bool:
        return self.machine_written or self.sha in BOOTSTRAP_COMMITS


def parse_log(output: str) -> list[Commit]:
    """Read `git log --pretty=%H|%ae|%s` output."""
    commits = []
    for line in output.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append(Commit(sha=parts[0], author_email=parts[1], subject=parts[2]))
    return commits


def offenders(commits: list[Commit]) -> list[Commit]:
    """Commits on the evidence branch that no machine wrote."""
    return [commit for commit in commits if not commit.allowed]


def read_history(repository: Path) -> list[Commit]:
    """The commit history of the checked out evidence branch."""
    output = subprocess.run(
        ["git", "log", "--pretty=%H|%ae|%s"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return parse_log(output)


def main() -> None:
    """Command line entry point. Non zero exit stops the publish."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("published"))
    args = parser.parse_args()

    commits = read_history(args.repository)
    unexpected = offenders(commits)
    if unexpected:
        print("The evidence branch carries commits that CI did not write:")
        for commit in unexpected:
            print(f"  {commit.sha[:7]} {commit.author_email} {commit.subject}")
        print("Publishing stops here. The ledger is not appended to.")
        sys.exit(1)

    print(f"{len(commits)} commits on the evidence branch, all accounted for")


if __name__ == "__main__":
    main()
