from __future__ import annotations

import pytest

from app.storage.local import ArmazenamentoLocal


def test_health_ok(cliente):
    assert cliente.get("/health").json() == {"status": "ok"}


def test_health_banco_fora(cliente, monkeypatch):
    monkeypatch.setattr("app.api.routes.sistema.banco_ok", lambda: False)
    r = cliente.get("/health")
    assert r.status_code == 503 and r.json()["reason"] == ["database"]


def test_config_publica(cliente):
    c = cliente.get("/api/config").json()
    assert c["env"] == "local" and c["login_dev"] is True and c["login_microsoft"] is False
    assert c["version"]


def test_storage_local_ida_e_volta(tmp_path):
    s = ArmazenamentoLocal(str(tmp_path))
    s.salvar("2026/10/REE-1/nota.pdf", b"%PDF", "application/pdf")
    assert s.abrir("2026/10/REE-1/nota.pdf") == b"%PDF"
    s.remover("2026/10/REE-1/nota.pdf")
    assert s.saudavel()


def test_storage_local_bloqueia_fuga_de_pasta(tmp_path):
    s = ArmazenamentoLocal(str(tmp_path / "raiz"))
    with pytest.raises(ValueError):
        s.salvar("../fora.txt", b"x", "text/plain")
