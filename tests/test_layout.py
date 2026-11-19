"""Regressões do layout de dezenas de hosts no dashboard."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_host_navigation_is_constrained_and_searchable():
    markup = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/css/dashboard.css").read_text(encoding="utf-8")

    assert 'id="overview-host-search"' in markup
    assert 'id="server-host-search"' in markup
    assert 'id="overview-hosts"' in markup
    assert 'id="server-tabs"' in markup
    assert ".host-rail" in styles
    assert "grid-template-columns:minmax(0,1.45fr) minmax(0,1fr)" in styles
    assert "overflow-x:auto" in styles


def test_browser_uses_backend_normalized_gauges():
    script = (ROOT / "app/static/js/hosts.js").read_text(encoding="utf-8")
    routes = (ROOT / "app/routes/monitoring.py").read_text(encoding="utf-8")

    assert "include_gauges=1" in script
    assert "monitoring.gauge_metrics(data)" in routes
    assert "function inferGauges" not in script


def test_single_orchestrator_is_preserved():
    assert [p.name for p in ROOT.glob("*.py")] == ["main.py"]
