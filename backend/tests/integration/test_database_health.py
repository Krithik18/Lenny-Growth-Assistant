from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.schema_version import SCHEMA_REVISION
from app.main import create_app


def test_readiness_revision_matches_migration_head():
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    assert ScriptDirectory.from_config(config).get_current_head() == SCHEMA_REVISION


@pytest.mark.parametrize("state,expected_code,expected_database", [
    ("ready", 200, "ready"),
    ("missing", 503, "migration_required"),
    ("old", 503, "migration_required"),
    ("down", 503, "unavailable"),
])
def test_readiness_database_states(state, expected_code, expected_database):
    app = create_app(Settings(_env_file=None, database_url=""))
    with TestClient(app) as client:
        connection = AsyncMock()
        if state == "down":
            connection.scalar.side_effect = OperationalError("SELECT", {}, Exception("private details"))
        elif state == "missing":
            connection.scalar.return_value = None
        else:
            connection.scalar.side_effect = ["app_data.alembic_version", SCHEMA_REVISION if state == "ready" else "old"]
        manager = AsyncMock()
        manager.__aenter__.return_value = connection
        engine = MagicMock()
        engine.connect.return_value = manager
        app.state.database = SimpleNamespace(engine=engine)
        response = client.get("/health/ready")
        assert response.status_code == expected_code
        assert response.json()["database"] == expected_database
        assert "private details" not in response.text
        assert client.get("/health/live").status_code == 200
