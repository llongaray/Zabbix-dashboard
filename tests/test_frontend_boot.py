"""Regressão: inicialização do navegador e detecção da origem do token."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_ROOT = ROOT / "app" / "static" / "js"


def test_navigation_iterates_all_matching_elements():
    """querySelector retorna um elemento, não uma coleção iterável."""
    source = (JS_ROOT / "hosts.js").read_text(encoding="utf-8")
    assert "for (const arrow of $$('[data-scroll-target]'))" in source
    assert "for (const arrow of $('[data-scroll-target]'))" not in source


def test_settings_load_independently_from_catalog():
    source = (JS_ROOT / "settings.js").read_text(encoding="utf-8")
    assert "await requestJSON('/api/config')" in source
    assert "await requestJSON('/api/catalog')" in source
    assert "Promise.all" not in source
    assert "config.token_source" in source


def test_frontend_has_error_boundary():
    source = (JS_ROOT / "dashboard.js").read_text(encoding="utf-8")
    assert "initialize().catch(" in source
    assert "Erro na inicialização" in source


def test_sources_never_render_raw_token():
    source = (JS_ROOT / "settings.js").read_text(encoding="utf-8")
    assert "config.token_source" in source
    assert "config.zabbix_api_token" not in source
