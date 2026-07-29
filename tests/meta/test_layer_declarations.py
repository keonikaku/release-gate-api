"""Meta layer: every test states its layer, and the statement is true.

The claim this repository makes is that test layer choices were deliberate. A
claim like that is worth nothing unless something enforces it, so this is the
enforcement: a test whose docstring does not name its layer, name the
requirements it covers, and justify the layer choice, fails the build.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parents[1]
LAYERS = {"unit", "contract", "integration", "meta"}
LABELS = ("Layer", "Covers", "Why this layer")
MINIMUM_REASON_LENGTH = 30


def collect_test_functions() -> list[tuple[str, str, ast.FunctionDef]]:
    """Every test function in the suite, with the layer directory it lives in."""
    found = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        layer = next((part for part in path.parts if part in LAYERS), None)
        assert layer is not None, f"{path} is not inside a layer directory"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.append((str(path.relative_to(TESTS_ROOT)), layer, node))
    return found


def docstring_field(doc: str, label: str) -> str | None:
    """The value of a `Label: value` line in a docstring, joined across wraps."""
    lines = [line.strip() for line in doc.splitlines()]
    for index, line in enumerate(lines):
        if not line.startswith(f"{label}:"):
            continue
        value = [line[len(label) + 1 :].strip()]
        for continuation in lines[index + 1 :]:
            starts_new_field = any(continuation.startswith(f"{other}:") for other in LABELS)
            if not continuation or starts_new_field:
                break
            value.append(continuation)
        return " ".join(value).strip()
    return None


ALL_TESTS = collect_test_functions()


def test_the_suite_was_discovered():
    """The collector below found tests. Guards every case in this file.

    Layer: meta
    Covers: none
    Why this layer: an empty collection would make every other check in this
    file pass by finding nothing, which is the classic vacuous gate.
    """
    assert len(ALL_TESTS) >= 40


def faults_in(module: str, layer: str, node: ast.FunctionDef) -> list[str]:
    """Everything wrong with one test's declaration, or an empty list."""
    name = f"{module}::{node.name}"
    doc = ast.get_docstring(node)
    if not doc:
        return [f"{name}: no docstring"]

    faults = []
    declared = docstring_field(doc, "Layer")
    if declared not in LAYERS:
        faults.append(f"{name}: declares layer {declared!r}")
    elif declared != layer:
        faults.append(f"{name}: declares layer {declared!r} but lives in {layer!r}")

    if not docstring_field(doc, "Covers"):
        faults.append(f"{name}: does not say what it covers")

    reason = docstring_field(doc, "Why this layer")
    if not reason or len(reason) < MINIMUM_REASON_LENGTH:
        faults.append(f"{name}: does not justify its layer")
    return faults


def test_every_test_declares_its_layer_and_justifies_it():
    """Each test names its layer, the requirements it covers, and why it is not
    at a different layer.

    Layer: meta
    Covers: none
    Why this layer: it reads the source of the suite rather than running any of
    it, so it cannot live at a layer that exercises the service. It is one case
    reporting every offender rather than one case per test, so that the layer
    counts this file also asserts stay a description of the suite rather than of
    its own parametrisation.
    """
    faults = [
        fault
        for module, layer, node in ALL_TESTS
        for fault in faults_in(module, layer, node)
    ]
    assert faults == [], "\n".join(faults)


def test_every_layer_has_tests_in_it():
    """All four layers are populated.

    Layer: meta
    Covers: none
    Why this layer: a layer that quietly empties would make the pyramid a
    drawing rather than a count.
    """
    populated = {layer for _, layer, _ in ALL_TESTS}
    assert populated == LAYERS


def test_the_unit_layer_is_the_widest():
    """More unit cases than integration cases.

    Layer: meta
    Covers: none
    Why this layer: the shape of the suite is a property of the suite. This is
    the pyramid, asserted rather than drawn.
    """
    counts = {layer: 0 for layer in LAYERS}
    for _, layer, _ in ALL_TESTS:
        counts[layer] += 1
    assert counts["unit"] > counts["integration"], counts
