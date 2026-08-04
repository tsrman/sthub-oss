import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import QuotaExceededError
from app.services.quota_service import RUNNING_STATUS, QuotaService


@pytest.fixture
def user_id():
    return uuid.uuid4()


def _mock_db(count: int) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = count
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_count_running_returns_count(user_id):
    db = _mock_db(3)
    service = QuotaService(max_running=5)

    count = await service.count_running(db, user_id)

    assert count == 3
    db.execute.assert_awaited_once()
    # Verify the query filters on the canonical running status constant.
    stmt = db.execute.call_args[0][0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    assert f"status = '{RUNNING_STATUS}'" in str(compiled)


@pytest.mark.asyncio
async def test_check_running_quota_ok(user_id):
    db = _mock_db(2)
    service = QuotaService(max_running=5)

    await service.check_running_quota(db, user_id)


@pytest.mark.asyncio
async def test_check_running_quota_exceeded_at_limit(user_id):
    db = _mock_db(5)
    service = QuotaService(max_running=5)

    with pytest.raises(QuotaExceededError) as exc_info:
        await service.check_running_quota(db, user_id)

    assert exc_info.value.code == "quota_exceeded"
    assert exc_info.value.limit == 5
    assert exc_info.value.current == 5
    assert "Running-app quota exceeded: 5/5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_running_quota_exceeded_over_limit(user_id):
    db = _mock_db(6)
    service = QuotaService(max_running=5)

    with pytest.raises(QuotaExceededError) as exc_info:
        await service.check_running_quota(db, user_id)

    assert exc_info.value.code == "quota_exceeded"
    assert exc_info.value.limit == 5
    assert exc_info.value.current == 6
    assert "Running-app quota exceeded: 6/5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_running_quota_logs_warning_on_exceed(user_id, caplog):
    db = _mock_db(5)
    service = QuotaService(max_running=5)

    with caplog.at_level("WARNING", logger="app.services.quota_service"):
        with pytest.raises(QuotaExceededError):
            await service.check_running_quota(db, user_id)

    assert "Quota exceeded" in caplog.text
    assert str(user_id) in caplog.text


def test_service_uses_settings_defaults():
    """QuotaService() without arguments should read defaults from get_settings()."""
    with patch("app.services.quota_service.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.MAX_RUNNING_APPS_PER_USER = 42
        mock_get_settings.return_value = mock_settings

        service = QuotaService()

        assert service.max_running == 42


def test_quota_exceeded_error_attributes():
    exc = QuotaExceededError(
        message="Running-app quota exceeded: 5/5",
        limit=5,
        current=5,
    )

    assert exc.code == "quota_exceeded"
    assert exc.limit == 5
    assert exc.current == 5
    assert str(exc) == "Running-app quota exceeded: 5/5"


@pytest.mark.asyncio
async def test_quota_exceeded_handler_includes_details():
    from app.main import quota_exceeded_handler

    exc = QuotaExceededError(
        message="Running-app quota exceeded: 5/5",
        limit=5,
        current=5,
    )

    response = await quota_exceeded_handler(MagicMock(), exc)

    assert response.status_code == 409
    body = json.loads(response.body)
    assert body == {
        "error": {
            "code": "quota_exceeded",
            "message": "Running-app quota exceeded: 5/5",
            "details": {"limit": 5, "current": 5},
        }
    }


@pytest.mark.asyncio
async def test_run_streamlit_returns_409_when_quota_exceeded(user_id):
    from app.dependencies import get_current_user_with_login
    from app.db.session import get_db
    from app.main import app

    app_id = uuid.uuid4()
    app_obj = MagicMock()
    app_obj.id = app_id
    app_obj.status = "stopped"
    app_obj.container_id = None

    user = MagicMock()
    user.username = "testuser"

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = app_obj
    db.execute.return_value = result

    async def override_get_db():
        return db

    def override_get_current_user_with_login():
        return user_id, "testuser", user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_with_login] = (
        override_get_current_user_with_login
    )

    try:
        with patch("app.api.streamlits.QuotaService") as MockQuota:
            instance = MockQuota.return_value
            instance.check_running_quota = AsyncMock(
                side_effect=QuotaExceededError(
                    message="Running-app quota exceeded: 5/5",
                    limit=5,
                    current=5,
                )
            )

            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                response = client.post(f"/api/v1/streamlits/{app_id}/run")

        assert response.status_code == 409
        payload = response.json()
        assert payload["error"]["code"] == "quota_exceeded"
        assert "quota" in payload["error"]["message"]
        assert payload["error"]["details"] == {"limit": 5, "current": 5}
    finally:
        app.dependency_overrides.clear()
