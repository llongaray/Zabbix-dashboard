"""Bateria estrutural dos quatro gráficos, sem screenshots frágeis."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_four_resource_charts_and_alert_bands():
    html = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
    for kind in ("cpu", "memory", "gpu", "network"):
        assert 'id="chart-' + kind + '"' in html
        assert 'id="history-message-' + kind + '"' in html
    for label in ("Atenção", "Crítico", "Máximo"):
        assert label in html


def test_history_renders_cache_before_remote_api():
    src = (ROOT / "app/static/js/history.js").read_text(encoding="utf-8")
    assert "await loadLocal(hostId, currentGeneration)" in src
    assert "loadOfficial(hostId, days, kind, currentGeneration)" in src


def test_worker_is_independent_docker_service():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "  collector:" in compose
    assert '["python", "-m", "app.worker"]' in compose
    assert "pgdata:" in compose
