"""Testes básicos de arquitetura e utilitários."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_python_entrypoint():
    assert sorted(p.name for p in ROOT.glob("*.py")) == ["main.py"]


def test_required_modules():
    for path in ("app/__init__.py", "app/db.py", "app/security.py", "app/services/zabbix.py", "app/routes/__init__.py"):
        assert (ROOT / path).is_file()
