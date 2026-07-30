"""Risk ratings, read from the document the author maintains.

**Nothing here infers a rating.** A risk rating is a judgement about what it
would cost if a rule were wrong in production, and inventing one on the author's
behalf would be the same defect as inventing a test result. The parser reads
`docs/risk-ratings.md` and treats anything that is not one of the three ratings
as unrated.

The published view is generated only from ratings that are actually recorded. If
none are, the section does not appear at all, because a page full of "pending"
is not evidence of anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RATINGS_FILE = REPO_ROOT / "docs" / "risk-ratings.md"

RATINGS = ("high", "medium", "low")
ROW = re.compile(r"^\|\s*(REQ-[\d.a-z]+)\s*\|\s*([A-Za-z]+)\s*\|\s*(.*?)\s*\|\s*$")


@dataclass(frozen=True)
class Rating:
    """One requirement, the risk the author assigned it, and why."""

    requirement: str
    rating: str
    reasoning: str

    @property
    def recorded(self) -> bool:
        """True when this is a real rating rather than a placeholder."""
        return self.rating.lower() in RATINGS


def parse(path: Path | None = None) -> tuple[Rating, ...]:
    """Read every row of the ratings table, rated or not."""
    file = RATINGS_FILE if path is None else path
    if not file.exists():
        return ()
    ratings = []
    for line in file.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line.strip())
        if match:
            requirement, rating, reasoning = match.groups()
            ratings.append(
                Rating(
                    requirement=requirement,
                    rating=rating.lower(),
                    reasoning=reasoning,
                )
            )
    return tuple(ratings)


def recorded(path: Path | None = None) -> dict[str, Rating]:
    """Only the requirements that carry a real rating."""
    return {r.requirement: r for r in parse(path) if r.recorded}
