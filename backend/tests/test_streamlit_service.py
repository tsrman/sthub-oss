"""Unit tests for StreamlitService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.streamlit import StreamlitApp
from app.services.lint_service import LintService
from app.services.streamlit_service import StreamlitService


@pytest.fixture
def service() -> StreamlitService:
    return StreamlitService()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_get_or_404_returns_app_when_found(
    service: StreamlitService, mock_db: AsyncMock
):
    app_id = uuid4()
    user_id = uuid4()
    expected_app = MagicMock(spec=StreamlitApp)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = expected_app
    mock_db.execute.return_value = result_mock

    app = await service.get_or_404(mock_db, app_id, user_id)

    assert app is expected_app
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_404_raises_when_not_found(
    service: StreamlitService, mock_db: AsyncMock
):
    app_id = uuid4()
    user_id = uuid4()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result_mock

    with pytest.raises(ValueError, match="Streamlit not found"):
        await service.get_or_404(mock_db, app_id, user_id)


def test_validate_requirements_delegates_to_lint(service: StreamlitService):
    with patch.object(
        service.lint, "validate_requirements", return_value=(True, [])
    ) as mock_validate:
        result = service.validate_requirements("pandas\nnumpy")

    mock_validate.assert_called_once_with("pandas\nnumpy")
    assert result == (True, [])


@pytest.mark.asyncio
async def test_check_syntax_delegates_to_lint(service: StreamlitService):
    expected = [{"line": 1, "message": "syntax error"}]
    with patch.object(
        service.lint, "check_syntax", new=AsyncMock(return_value=expected)
    ) as mock_check:
        result = await service.check_syntax("invalid code")

    mock_check.assert_awaited_once_with("invalid code")
    assert result is expected


@pytest.mark.asyncio
async def test_lint_service_can_be_injected():
    mock_lint = MagicMock(spec=LintService)
    service = StreamlitService(lint_service=mock_lint)

    assert service.lint is mock_lint

    mock_lint.validate_requirements.return_value = (True, [])
    assert service.validate_requirements("requests") == (True, [])

    expected_issues = [{"line": 2, "message": "unused import"}]
    mock_lint.check_syntax.return_value = expected_issues
    assert await service.check_syntax("import os") is expected_issues
