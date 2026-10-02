from pathlib import Path

import pytest
from backend.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client
