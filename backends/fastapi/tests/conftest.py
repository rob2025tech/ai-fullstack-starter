import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None)))
