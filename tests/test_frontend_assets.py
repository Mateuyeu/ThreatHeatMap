"""Source-level anti-regression tests for the heat map JS.

Two bugs from sub-pass C.2 are guarded here:

1. Double HTML-encoding of the MITRE fallback label. The JS string used as
   the fallback link text must contain a literal `&`, not `&amp;`, otherwise
   `escapeHtml()` produces `&amp;amp;` and the user sees `MITRE ATT&amp;CK`.
2. Quadrant separator shapes silently dropped. The `layout.shapes` block
   must hold two `type: "line"` entries: one vertical at `x0/x1 = tx`, one
   horizontal at `y0/y1 = ty`, both anchored on the data axes
   (`xref: "x"`, `yref: "y"`).

We assert against the source rather than spinning up a JS engine: the bugs
are syntactic regressions (someone deleted/edited the wrong string), so a
text check is the right granularity.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "static" / "js" / "heatmap.js"


@pytest.fixture(scope="module")
def js_source():
    return JS_PATH.read_text(encoding="utf-8")


# --- Bug 1: MITRE label must not pre-encode `&` -------------------------

def test_mitre_fallback_label_uses_literal_amp(js_source):
    """The fallback link text must contain a literal `&` so escapeHtml encodes
    it exactly once at render time (yielding `&amp;` in the DOM, displayed as
    `&` to the user)."""
    # Find every "MITRE ATT...CK" string literal in the JS.
    matches = re.findall(r'"(MITRE ATT[^"]*?CK)"', js_source)
    assert matches, "Could not find any MITRE ATT*CK string literal in heatmap.js"
    for m in matches:
        assert "&amp;" not in m, (
            f"MITRE label {m!r} pre-encodes `&amp;`; escapeHtml will double-encode "
            "and surface `MITRE ATT&amp;CK` to the user"
        )
        # Allow either no ampersand at all (e.g. "MITRE ATTACK"-style
        # truncations) or a single literal `&`.
        if "&" in m:
            assert "&amp;" not in m


# --- Bug 2: quadrant separator shapes must be present and data-anchored ---

def _layout_shapes_block(js_source):
    """Return the substring inside `shapes: [ ... ]` from renderHeatmap's
    layout. Helper used by the next two assertions."""
    match = re.search(r"shapes:\s*\[(?P<body>.*?)\]\s*,", js_source, re.DOTALL)
    assert match, "Could not locate `shapes:` array in heatmap.js"
    return match.group("body")


def test_quadrant_shapes_block_has_two_line_shapes(js_source):
    body = _layout_shapes_block(js_source)
    line_count = len(re.findall(r'type:\s*"line"', body))
    assert line_count == 2, (
        f"Expected 2 line shapes (vertical + horizontal quadrants); found {line_count}"
    )


def test_quadrant_shapes_anchor_on_data_axes(js_source):
    """Without explicit xref/yref Plotly defaults to 'paper' on some 2D layouts,
    which would render the lines off-screen."""
    body = _layout_shapes_block(js_source)
    assert re.search(r'xref:\s*"x"', body), "vertical/horizontal shape missing xref:'x'"
    assert re.search(r'yref:\s*"y"', body), "vertical/horizontal shape missing yref:'y'"


def test_vertical_quadrant_line_uses_threshold_x(js_source):
    body = _layout_shapes_block(js_source)
    # Vertical line: x0 = x1 = tx
    assert re.search(r"x0:\s*tx\s*,\s*x1:\s*tx", body), (
        "Vertical quadrant line must use x0/x1 = tx (config.QUADRANT_THRESHOLD_X)"
    )


def test_horizontal_quadrant_line_uses_threshold_y(js_source):
    body = _layout_shapes_block(js_source)
    # Horizontal line: y0 = y1 = ty
    assert re.search(r"y0:\s*ty\s*,\s*y1:\s*ty", body), (
        "Horizontal quadrant line must use y0/y1 = ty (config.QUADRANT_THRESHOLD_Y)"
    )


def test_quadrant_thresholds_pulled_from_api_config(js_source):
    """The frontend must read the thresholds from /api/config so the backend
    knobs in config.py actually take effect."""
    assert "quadrant_threshold_x" in js_source
    assert "quadrant_threshold_y" in js_source


# --- C.3: enriched context banner --------------------------------------

def test_context_banner_renders_all_required_fields(js_source):
    """The banner must surface Sector, Window (since -> until), Client
    profile, and Data extracted (UTC). Source-level smoke check."""
    assert "renderContextBanner" in js_source, "renderContextBanner function missing"
    for label in ["Sector:", "Window:", "Client profile:", "Data extracted:"]:
        assert label in js_source, f"context banner missing {label!r} label"


def test_context_banner_uses_extracted_at_and_until(js_source):
    """The banner must consume both new payload fields, not fabricate them."""
    assert "data.extracted_at" in js_source or "extracted_at" in js_source
    assert "data.until" in js_source or "data.until" in js_source


# --- C.3: SecurityScore Apply button -----------------------------------

def test_security_score_not_in_change_listener_array(js_source):
    """Per C.3, SecurityScore Override must NOT trigger a recalc on every
    keystroke. Only Apply click or Enter key should fire onFilterChange."""
    # The change-listener array binds these IDs to onFilterChange directly.
    match = re.search(r'\[\s*"sector"\s*,\s*"window"\s*,\s*"client"\s*\]', js_source)
    assert match, "Could not locate the change-listener array; if you renamed it, update this test"
    assert "security_score" not in match.group(0), (
        "security_score must not be in the change-listener array (recalc should "
        "only fire on Apply / Enter)"
    )


def test_security_score_apply_button_wired(js_source):
    assert "applySecurityScore" in js_source, "applySecurityScore handler missing"
    assert "security_score_apply" in js_source, "Apply button id reference missing"
    # Enter key handling on the input itself
    assert re.search(r'security_score.*keydown', js_source, re.DOTALL), (
        "Enter-key handler on security_score input not wired"
    )


def test_security_score_validates_0_to_100(js_source):
    """Validation must reject values outside [0, 100] before applying."""
    assert "v < 0 || v > 100" in js_source, (
        "Validation guard for SecurityScore range [0, 100] missing"
    )


# --- C.3: Refresh button disabled on fixture ----------------------------

def test_refresh_disabled_when_active_adapter_is_fixture(js_source):
    assert "disableRefreshIfFixture" in js_source
    assert 'active_victims_adapter === "fixture"' in js_source, (
        "Refresh button must be disabled when active_victims_adapter is the fixture"
    )
    # The C.3 spec mandates the explicit tooltip text
    assert "Phase 2 (MITRE STIX/TAXII connector)" in js_source


# --- C.3: methodology link in footer -----------------------------------

INDEX_PATH = (Path(__file__).resolve().parents[1]) / "templates" / "index.html"


def test_index_html_links_to_methodology():
    html = INDEX_PATH.read_text(encoding="utf-8")
    assert 'href="/methodology"' in html, "Footer methodology link missing"
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
