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
import re
import subprocess
from pathlib import Path

from tools import defects

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
    collect_failure_log(out, runs_data)


SMOKE_LINE = re.compile(r"^(ok\s|FAIL\s|\s+the service said)")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def collect_failure_log(out: Path, runs_data: list[dict]) -> None:
    """Keep the smoke output of the most recent blocked run on main.

    The page shows one real failure: what was expected, what came back, and
    which run. Those numbers are not typed anywhere. They are lifted out of
    GitHub's own log for that run, which is the strongest source available and
    not one this repository can edit.
    """
    blocked = next(
        (
            run
            for run in runs_data
            if run.get("headBranch") == "main"
            and any(
                job["name"].startswith("Verify") and job.get("conclusion") == "failure"
                for job in run.get("jobs", [])
            )
        ),
        None,
    )
    if not blocked:
        print("no blocked run on main; writing no failure log")
        return

    log = gh("run", "view", str(blocked["databaseId"]), "--log-failed")
    if log is None:
        print("could not read the failed run log")
        return

    lines = []
    for raw in log.splitlines():
        text = ANSI.sub("", raw)
        # Drop the job, step and timestamp columns the log viewer prefixes.
        parts = text.split("\t")
        body = parts[-1]
        body = re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s?", "", body)
        if SMOKE_LINE.match(body):
            lines.append(body.rstrip())

    if not lines:
        print("the failed run log carried no smoke output")
        return

    (out / "failure-log.json").write_text(
        json.dumps(
            {
                "run_id": str(blocked["databaseId"]),
                "url": blocked.get("url", ""),
                "commit_sha": blocked.get("headSha", ""),
                "commit_message": blocked.get("headCommitMessage", ""),
                "created_at": blocked.get("createdAt", ""),
                "lines": lines,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"kept {len(lines)} lines of smoke output from run {blocked['databaseId']}")


def collect_commits(out: Path, shas: list[str]) -> None:
    """Details of named commits, so the defect report does not restate them.

    The report names the commits by SHA, because a SHA is a fact anyone can
    check. Everything else about them (the message, who authored it, when) is
    read from GitHub here rather than typed into the report, where it could
    drift from the commit it describes.
    """
    found = {}
    for sha in shas:
        raw = gh("api", f"repos/{{owner}}/{{repo}}/commits/{sha}")
        if raw is None:
            print(f"could not read commit {sha}")
            continue
        commit = json.loads(raw)
        found[sha] = {
            "sha": commit["sha"],
            "short_sha": commit["sha"][:7],
            "message": commit["commit"]["message"].splitlines()[0],
            "authored_at": commit["commit"]["author"]["date"],
            "url": commit["html_url"],
        }
    if found:
        (out / "commits.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
        print(f"read {len(found)} commits")


def collect_pulls(out: Path, numbers: list[int]) -> None:
    """Title, merge time and URL for the pull requests a defect refers to."""
    found = {}
    for number in numbers:
        raw = gh("pr", "view", str(number), "--json", "number,title,url,mergedAt,state")
        if raw is None:
            print(f"could not read pull request {number}")
            continue
        found[str(number)] = json.loads(raw)
    if found:
        (out / "pulls.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
        print(f"read {len(found)} pull requests")


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

    # Whatever the defect reports name, so the pages can render the facts about
    # those commits and pull requests instead of repeating them.
    referenced = defects.referenced_commits()
    if referenced:
        collect_commits(args.out, referenced)
    pulls = defects.referenced_pulls()
    if pulls:
        collect_pulls(args.out, pulls)


if __name__ == "__main__":
    main()
