"""Drive a freshly built instance over real HTTP.

The suite drives the application in process, which is fast and deterministic and
proves nothing about serving. This script talks to a running server on a
database that did not exist a moment ago: one accepted submission, one refusal,
one illegal transition. If any of those three answers is wrong the process exits
non zero and the verify job fails, which is what stops promotion.

Usage: python -m tools.smoke http://127.0.0.1:8000
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

from tests.factories import on_call_entry, valid_payload

TIMEOUT_SECONDS = 10


def decode(raw: bytes) -> dict:
    """Read a JSON body, or report what arrived instead.

    A served instance can fail in ways that produce no JSON at all: an
    unhandled exception returns a plain text 500. Letting that raise here
    replaced the failing check with a traceback about JSON, which hid which
    call had failed. The run log of a blocked deployment is something people
    read, so it says what happened.
    """
    import json  # noqa: PLC0415 - local to keep this script import light

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {"unparsed_body": raw.decode("utf-8", "replace")[:400]}


def call(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    """One request. Returns the status and the decoded body."""
    import json  # noqa: PLC0415 - local to keep this script import light

    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed localhost target
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, decode(error.read())
    except urllib.error.URLError as error:
        print(f"FAIL  {method} {url}: the service did not answer ({error.reason})")
        raise SystemExit(1) from error


def check(label: str, actual, expected, context: object = None) -> None:
    """Print the result and exit on the first disagreement."""
    if actual != expected:
        print(f"FAIL  {label}: expected {expected}, got {actual}")
        if context:
            print(f"      the service said: {context}")
        raise SystemExit(1)
    print(f"ok    {label}")


def main(base: str) -> None:
    """Three cases against the live instance."""
    status, health = call("GET", f"{base}/healthz")
    check("healthz responds", status, 200)
    check("healthz reports ok", health["status"], "ok")

    status, accepted = call("POST", f"{base}/changes", valid_payload())
    check("a change is created", status, 201, accepted)
    status, submitted = call("POST", f"{base}/changes/{accepted['id']}/submit")
    check("a valid submission is accepted", status, 200, submitted)

    status, refused = call(
        "POST",
        f"{base}/changes",
        valid_payload(
            release_type="sprint",
            on_call=[on_call_entry("devops")],
        ),
    )
    check("a second change is created", status, 201)
    status, body = call("POST", f"{base}/changes/{refused['id']}/submit")
    check("an understaffed submission is refused", status, 400)
    check(
        "the refusal names REQ-1.6",
        [v["rule"] for v in body["detail"]["violations"]],
        ["REQ-1.6"],
    )

    status, body = call(
        "POST",
        f"{base}/changes/{accepted['id']}/transition",
        {"to_state": "closed"},
    )
    check("an illegal transition is refused", status, 409)
    check("the refusal is machine readable", body["detail"]["code"], "illegal_transition")

    print("smoke: the freshly built instance behaves")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
