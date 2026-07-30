"""Shared HTML pieces: the shell, the styles, and how a timestamp is shown.

Kept apart from `build_site.py` so the page builders stay about content and so
the timestamp rule has one implementation that every page uses.

**The timestamp rule.** A raw UTC stamp misreads for anyone who is not on UTC,
and the author is ten hours behind it: a release cut at 15:15 in Honolulu
renders as 01:15 the next day. Every timestamp on this site therefore ships as
Honolulu time with the zone named, wrapped in a `<time>` element that carries
the machine readable value. A small script then rewrites it into the reader's
own timezone and adds how long ago it was. With the script blocked the page
still shows a named zone and a real time, which is the point of doing it this
way rather than in the reader's browser alone.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta, timezone

# Honolulu has never observed daylight saving, so a fixed offset is exactly
# right all year and needs no timezone database on the runner.
HONOLULU = timezone(timedelta(hours=-10), "HST")

STYLES = """
:root{
  --bg:#0a0e14; --bg-soft:#0d1219; --panel:#111826; --line:#232e40;
  --line-soft:#1a2434; --txt:#eef2f7; --muted:#8b9bb0; --muted-dim:#5c6c81;
  --accent:#4fd1ff; --green:#34d399; --red:#f87171; --amber:#fbbf24;
  --grad:linear-gradient(120deg,#4fd1ff 0%,#7c9cff 55%,#34d399 100%);
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,'SFMono-Regular',Menlo,Consolas,monospace;
  --radius:16px; --shadow:0 20px 50px -20px rgba(0,0,0,.55);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);
  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px 80px}
header.top{border-bottom:1px solid var(--line);background:var(--bg-soft);
  position:sticky;top:0;z-index:5}
header.top .wrap{padding:16px 24px;display:flex;gap:20px;align-items:baseline;
  flex-wrap:wrap}
header.top strong{font-size:15px;letter-spacing:.2px}
nav a{color:var(--muted);font-size:13px;margin-right:16px}
nav a.here{color:var(--txt);border-bottom:2px solid var(--accent);padding-bottom:2px}
h1{font-size:30px;line-height:1.25;margin:36px 0 8px;letter-spacing:-.4px}
h2{font-size:20px;margin:40px 0 10px;letter-spacing:-.2px}
h3{font-size:15px;margin:26px 0 8px;color:var(--txt)}
p{color:var(--muted);margin:10px 0}
p.lede{color:var(--txt);font-size:16px;max-width:70ch}
.grid{display:grid;gap:16px}
.g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:20px 22px;box-shadow:var(--shadow)}
.card h3{margin-top:0}
.kpi{font-family:var(--mono);font-size:26px;letter-spacing:-.5px}
.label{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted-dim)}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:1px;
  color:var(--muted-dim);border-bottom:1px solid var(--line);padding:8px 10px;
  font-weight:600}
td{border-bottom:1px solid var(--line-soft);padding:9px 10px;vertical-align:top;
  color:var(--muted)}
td.k,td strong{color:var(--txt)}
code,.mono{font-family:var(--mono);font-size:12.5px}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 8px;
  border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.ok{color:var(--green);border-color:rgba(52,211,153,.35);background:rgba(52,211,153,.08)}
.bad{color:var(--red);border-color:rgba(248,113,113,.35);background:rgba(248,113,113,.08)}
.warn{color:var(--amber);border-color:rgba(251,191,36,.35);background:rgba(251,191,36,.08)}
.dim{color:var(--muted-dim)}
.banner{border-radius:var(--radius);padding:22px 24px;border:1px solid var(--line);
  background:var(--panel);display:flex;gap:22px;align-items:center;flex-wrap:wrap}
.banner .verdict{font-family:var(--mono);font-size:34px;letter-spacing:-1px}
.verdict.go{color:var(--green)} .verdict.nogo{color:var(--red)}
pre{background:var(--bg-soft);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px;overflow:auto;font-family:var(--mono);font-size:12px;
  color:#cfe3f5;margin:8px 0}
.exchange{border:1px solid var(--line);border-radius:12px;margin:12px 0;overflow:hidden}
.exchange summary{cursor:pointer;padding:12px 16px;background:var(--bg-soft);
  font-size:13.5px;color:var(--txt)}
.exchange .body{padding:4px 16px 16px}
.bar{height:8px;border-radius:6px;background:var(--line-soft);overflow:hidden}
.bar span{display:block;height:100%;background:var(--grad)}
footer{border-top:1px solid var(--line);margin-top:56px;padding-top:20px;
  color:var(--muted-dim);font-size:12.5px}
.note{border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin:16px 0;
  color:var(--muted)}
"""

TIME_SCRIPT = """
document.querySelectorAll('time.ts').forEach(function(el){
  var iso = el.getAttribute('datetime');
  var when = new Date(iso);
  if (isNaN(when)) { return; }
  var zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
  var shown = when.toLocaleString(undefined, {
    day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'
  });
  var seconds = (Date.now() - when.getTime()) / 1000;
  var units = [['year',31536000],['month',2592000],['day',86400],['hour',3600],
               ['minute',60]];
  var ago = 'just now';
  for (var i = 0; i < units.length; i++) {
    var size = Math.floor(seconds / units[i][1]);
    if (size >= 1) { ago = size + ' ' + units[i][0] + (size > 1 ? 's' : '') + ' ago'; break; }
  }
  el.textContent = shown + ' (' + zone + ', ' + ago + ')';
});
"""

NAV = (
    ("index.html", "Dashboard"),
    ("demo.html", "The two runs"),
    ("traceability.html", "Traceability"),
    ("evidence.html", "Evidence"),
    ("api.html", "API"),
    ("team.html", "How it was built"),
)


def esc(value: object) -> str:
    """HTML escape anything, including numbers and None."""
    return html.escape("" if value is None else str(value), quote=True)


def parse_iso(value: str) -> datetime | None:
    """Read an ISO timestamp, tolerating the Z suffix GitHub uses."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def time_tag(value: str | datetime | None, fallback: str = "not recorded") -> str:
    """A timestamp a reader can act on, in Honolulu time, upgraded by script."""
    moment = parse_iso(value) if isinstance(value, str) else value
    if moment is None:
        return f'<span class="dim">{esc(fallback)}</span>'
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone(HONOLULU)
    return (
        f'<time class="ts" datetime="{esc(moment.isoformat())}">'
        f"{local:%d %b %Y, %H:%M} HST</time>"
    )


def inline_markdown(text: str) -> str:
    """Render the inline markdown the documents use, and nothing else.

    The gaps and the open questions are published straight from
    `docs/test-design.md`, so that the page cannot drift from the document the
    build gate reads. Publishing them verbatim meant publishing `**bold**` and
    backticks as literal characters, which is the most reader visible defect a
    generated page can have and it was sitting in the honesty section.

    Escaping happens first, so no markup in the source document can inject HTML.
    """
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
    out = re.sub(r"(?<![*\w])\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    return out


def pill(text: str, kind: str = "") -> str:
    """A small status chip."""
    return f'<span class="pill {kind}">{esc(text)}</span>'


def outcome_pill(outcome: str | None, status: str = "") -> str:
    """A chip for a test or run outcome.

    A job with no conclusion has not finished. The publish job is the clearest
    case: it is running while it generates this page, so it can never report its
    own conclusion here. Rendering that as "not run" contradicted GitHub, which
    showed it as a success moments later.
    """
    if not outcome and status in ("in_progress", "queued", "requested", "waiting"):
        return pill("in progress", "warn")
    mapping = {
        "passed": "ok",
        "pass": "ok",
        "success": "ok",
        "failed": "bad",
        "fail": "bad",
        "failure": "bad",
        "error": "bad",
        "skipped": "warn",
        "startup_failure": "bad",
    }
    if not outcome:
        return pill("not run", "warn")
    return pill(outcome, mapping.get(outcome, "warn"))


def page(title: str, current: str, body: str, generated_at: datetime, sha: str) -> str:
    """The shell every page shares."""
    links = "".join(
        f'<a href="{href}"{' class="here"' if href == current else ""}>{esc(label)}</a>'
        for href, label in NAV
    )
    short = esc(sha[:7]) if sha else "unknown"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{STYLES}</style>
</head>
<body>
<header class="top"><div class="wrap">
<strong>Release Gate API</strong>
<nav>{links}</nav>
</div></header>
<main class="wrap">
{body}
<footer>
Every page here is generated by the post-merge workflow from the artifacts of a
real run. No number on this site is typed in. The sentences that explain what
you are looking at are written by a person; every figure, result, timestamp and
link beside them comes from the run.
Built from commit <code>{short}</code> at {time_tag(generated_at)}.
<br>
<a href="https://github.com/keonikaku/release-gate-api">Repository</a> &middot;
<a href="https://github.com/keonikaku/release-gate-api/actions/workflows/post-merge.yml">Run history</a>
</footer>
</main>
<script>{TIME_SCRIPT}</script>
</body>
</html>
"""
