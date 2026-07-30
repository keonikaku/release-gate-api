"""Read GitHub's own record of this repository into files the builder can use.

Every shell call to `gh` lives here, so the site builder stays a pure function of
files and can be tested without a network or a token.

If a query fails, this writes nothing for it rather than writing a zero. The
readout treats a criterion it could not evaluate as NO-GO, so a silent zero would
turn a failed lookup into a green tick, which is the one failure this design has
to avoid.

Usage:
    python -m tools.collect_github --out reports
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

WORKFLOW = "post-merge.yml"
RUN_FIELDS = "databaseId,conclusion,status,headBranch,headSha,createdAt,url,displayTitle"


def gh(*arguments: str) -> str | None:
    """Run a gh command. Returns None when it fails, never a fabricated value."""
    try:
        finished = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return finished.stdout


def collect_runs(out: Path, limit: int = 30) -> None:
    """Recent post-merge runs, each with the conclusion of each of its jobs."""
    listing = gh(
        "run", "list", "--workflow", WORKFLOW, "--limit", str(limit), "--json", RUN_FIELDS
    )
    if listing is None:
        print("could not list runs; writing nothing")
        return

    runs_data = json.loads(listing)
    for run in runs_data:
        jobs = gh("run", "view", str(run["databaseId"]), "--json", "jobs")
        run["jobs"] = json.loads(jobs)["jobs"] if jobs else []

        # `displayTitle` is truncated by GitHub, which cut the clause explaining
        # why a deliberate defect existed off the end of the sentence that said
        # it was deliberate. The full subject line comes from the commit itself.
        head = gh(
            "api",
            f"repos/{{owner}}/{{repo}}/commits/{run['headSha']}",
            "--jq",
            ".commit.message",
        )
        if head:
            run["headCommitMessage"] = head.strip().splitlines()[0]
    (out / "gh-runs.json").write_text(json.dumps(runs_data, indent=2), encoding="utf-8")
    print(f"wrote {len(runs_data)} runs")


def collect_blockers(out: Path) -> None:
    """How many open issues carry the release-blocker label."""
    listing = gh(
        "issue", "list", "--label", "release-blocker", "--state", "open", "--json", "number"
    )
    if listing is None:
        print("could not read issues; the readout will report C5 as not evaluated")
        return
    count = len(json.loads(listing))
    (out / "blockers.json").write_text(
        json.dumps({"open": count}, indent=2), encoding="utf-8"
    )
    print(f"open release-blocker issues: {count}")


def collect_production(out: Path) -> None:
    """The newest promoted release, which is what production means here."""
    listing = gh("release", "list", "--limit", "1", "--json", "tagName,publishedAt,name")
    if listing is None:
        print("could not read releases; writing nothing")
        return
    releases = json.loads(listing)
    if not releases:
        print("no release has been promoted yet")
        return

    latest = releases[0]
    tag = latest["tagName"]
    view = gh("release", "view", tag, "--json", "targetCommitish,tagName,publishedAt")
    commit = ""
    if view:
        commit = json.loads(view).get("targetCommitish", "")
    (out / "production.json").write_text(
        json.dumps(
            {
                "version": tag,
                "commit_sha": commit,
                "published_at": latest.get("publishedAt", ""),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"production is on {tag}")


def main() -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    collect_runs(args.out)
    collect_blockers(args.out)
    collect_production(args.out)


if __name__ == "__main__":
    main()
