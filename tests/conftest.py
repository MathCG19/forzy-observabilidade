import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        db_path=tmp_path / "teste.db",
        simular_latencia=False,
        prob_falha_fonte=0.0,
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-Session-Id": "sessao-teste", "X-Feature": "teste"}
