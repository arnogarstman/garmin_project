import json

from garminreader.snapshot import render


def test_payload_cannot_close_the_script_element() -> None:
    """Text from the warehouse (an activity name) must not end the inline <script> early."""
    html = render.render({"recent": [{"activity_name": "</script><b>x</b>"}]})
    assert "</script><b>" not in html
    start = html.index("window.__SNAPSHOT__=") + len("window.__SNAPSHOT__=")
    payload = html[start : html.index(";</script>", start)]
    assert json.loads(payload)["recent"][0]["activity_name"] == "</script><b>x</b>"


def test_template_markers_are_all_filled() -> None:
    html = render.render({})
    assert render.DATA_MARKER not in html
    assert render.APP_MARKER not in html
    assert "<title>" in html
