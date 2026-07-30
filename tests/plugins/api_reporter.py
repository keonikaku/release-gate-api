"""Print one readable line per API case while the suite runs.

Default pytest output is a row of dots. It proves the suite ran and nothing
about what it checked, which makes it useless to watch and useless to record.

This prints, for every case that carries a `Case:` annotation, the case ID, the
request it finished on, the status the service returned, and the result. The
lines come from the run itself: the status is read off the response the case
received, not from the docstring, so a case whose declared status is wrong shows
the disagreement on screen.

Off by default. `--api-log` switches it on, which is what the recording uses and
what makes a local run worth watching:

    pytest -m "integration or contract" --api-log
"""

from __future__ import annotations

import re

import pytest

CASE_LINE = re.compile(r"^\s*Case:\s*(API-\d+)\s*$", re.MULTILINE)
EXPECTS_LINE = re.compile(r"^\s*Expects:\s*(\d{3})\s*$", re.MULTILINE)

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the switch."""
    parser.addoption(
        "--api-log",
        action="store_true",
        default=False,
        help="Print one line per API case: id, request, status, result.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the plugin's own marker free state."""
    config._api_log_rows = []  # noqa: SLF001 - plugin state on the config object


def _annotation(item: pytest.Item, pattern: re.Pattern[str]) -> str:
    """Read one annotation out of the test's docstring."""
    doc = getattr(item, "function", None).__doc__ or "" if hasattr(item, "function") else ""
    found = pattern.search(doc)
    return found.group(1) if found else ""


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Nothing here: the line is printed from the teardown hook below, which is
    where the recorded exchanges are still reachable."""


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    """Print the case line after the test has run and its client is closed."""
    result = yield

    if not item.config.getoption("--api-log"):
        return result

    case_id = _annotation(item, CASE_LINE)
    if not case_id:
        return result

    expects = _annotation(item, EXPECTS_LINE)
    exchanges = getattr(item, "_api_exchanges", [])
    subject = exchanges[-1] if exchanges else None
    outcome = getattr(item, "_api_outcome", "unknown")

    passed = outcome == "passed"
    tick = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    request = f"{subject.method} {subject.path}" if subject else "no request recorded"
    status = str(subject.status) if subject else "-"
    agrees = subject is not None and str(subject.status) == expects
    status_colour = GREEN if agrees else RED

    line = (
        f"{BOLD}{case_id}{RESET} {tick}  "
        f"{status_colour}{status}{RESET} "
        f"{DIM}expected {expects}{RESET}  {request}"
    )
    print(f"\n{line}", flush=True)
    return result


def pytest_terminal_summary(
    terminalreporter, exitstatus: int, config: pytest.Config
) -> None:
    """Close with the spread of status codes the run actually produced."""
    if not config.getoption("--api-log"):
        return
    counts: dict[int, int] = {}
    for status in getattr(config, "_api_statuses", []):
        counts[status] = counts.get(status, 0) + 1
    if not counts:
        return
    spread = "  ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    terminalreporter.write_line("")
    terminalreporter.write_line(f"status codes returned by the service:  {spread}")
