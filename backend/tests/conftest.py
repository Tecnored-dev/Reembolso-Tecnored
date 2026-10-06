"""Fixtures: SQLite em memória no lugar do Postgres, storage numa pasta temporária."""

from __future__ import annotations

import os

os.environ.setdefault("DB_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "local")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.storage import get_armazenamento
from app.storage.local import ArmazenamentoLocal


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng, expire_on_commit=False)()
    yield session
    session.close()
    eng.dispose()


@pytest.fixture
def settings():
    return Settings(
        app_env="local",
        db_url="sqlite:///:memory:",
        grupo_gestor="g-gestor",
        grupo_financeiro="g-fin",
        grupo_admin="g-admin",
        dev_login_enabled=True,
        frontend_url="http://front",
    )


@pytest.fixture
def cliente(db, settings, tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr("app.api.routes.sistema.banco_ok", lambda: True)
    storage = ArmazenamentoLocal(str(tmp_path / "arquivos"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    get_armazenamento.cache_clear()
    monkeypatch.setattr("app.api.routes.sistema.get_armazenamento", lambda: storage)
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()
