from __future__ import annotations

import logging
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.core.validation import MAX_FILE_SIZE_BYTES, MAX_REQUIREMENTS_SIZE
from app.models import StreamlitFile
from app.services.file_service import FileService


def _make_file(streamlit_id: uuid.UUID, **kwargs: object) -> StreamlitFile:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "streamlit_id": streamlit_id,
        "path": "app.py",
        "content_type": "text/x-python",
        "content_text": "print('hello')",
        "content_bytes": None,
        "is_entrypoint": True,
    }
    defaults.update(kwargs)
    return StreamlitFile(**defaults)


def _make_scalar_one_or_none(value: StreamlitFile | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_scalar_one(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _make_scalars_all(values: list[StreamlitFile]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _async_db() -> AsyncMock:
    """Return an AsyncMock with sync session methods mocked as MagicMock."""
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def streamlit_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_list_files_empty(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    db.execute.return_value = _make_scalars_all([])

    files = await FileService().list_files(db, streamlit_id)

    assert files == []
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_files_orders_by_path(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    file_b = _make_file(streamlit_id=streamlit_id, path="b.py", content_text="b")
    file_a = _make_file(streamlit_id=streamlit_id, path="a.py", content_text="a")
    db.execute.return_value = _make_scalars_all([file_b, file_a])

    files = await FileService().list_files(db, streamlit_id)

    assert files == [file_b, file_a]
    db.execute.assert_awaited_once()
    stmt = db.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled
    assert "streamlit_files.path" in compiled


@pytest.mark.asyncio
async def test_get_file_found(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    expected = _make_file(streamlit_id=streamlit_id, path="app.py")
    db.execute.return_value = _make_scalar_one_or_none(expected)

    result = await FileService().get_file(db, streamlit_id, "app.py")

    assert result is expected


@pytest.mark.asyncio
async def test_get_file_not_found(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(None)

    result = await FileService().get_file(db, streamlit_id, "missing.py")

    assert result is None


@pytest.mark.asyncio
async def test_get_file_invalid_path_rejected(streamlit_id: uuid.UUID) -> None:
    db = _async_db()

    with pytest.raises(ValueError):
        await FileService().get_file(db, streamlit_id, "../bad.py")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_text_file(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]

    file = await service.save_file(db, streamlit_id, "app.py", "print('hi')")

    assert file.path == "app.py"
    assert file.content_text == "print('hi')"
    assert file.content_bytes is None
    assert file.is_entrypoint is True
    assert file.content_type == "text/x-python"
    db.add.assert_called_once_with(file)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_binary_file(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]
    data = b"\x89PNG\r\n\x1a\n"

    file = await service.save_file(db, streamlit_id, "image.png", data)

    assert file.content_bytes == data
    assert file.content_text is None
    assert file.content_type == "image/png"
    assert file.is_entrypoint is False
    db.add.assert_called_once_with(file)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_file(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    existing = _make_file(
        streamlit_id=streamlit_id,
        path="utils.py",
        content_text="old",
        content_type="text/x-python",
        is_entrypoint=False,
    )
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    file = await service.save_file(
        db, streamlit_id, "utils.py", "new", content_type="text/plain"
    )

    assert file is existing
    assert file.content_text == "new"
    assert file.content_bytes is None
    assert file.content_type == "text/plain"
    assert isinstance(file.updated_at, datetime)
    db.add.assert_not_called()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_file(streamlit_id: uuid.UUID) -> None:
    existing = _make_file(
        streamlit_id=streamlit_id, path="utils.py", is_entrypoint=False
    )
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    result = await FileService().delete_file(db, streamlit_id, "utils.py")

    assert result is True
    db.delete.assert_called_once_with(existing)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_file_not_found(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(None)

    result = await FileService().delete_file(db, streamlit_id, "missing.py")

    assert result is False
    db.delete.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.parametrize(
    "path", ["app.py", "requirements.txt", "APP.py", "Requirements.TXT"]
)
@pytest.mark.asyncio
async def test_delete_required_file_rejected(
    streamlit_id: uuid.UUID, path: str
) -> None:
    db = _async_db()

    with pytest.raises(ValueError, match="required file"):
        await FileService().delete_file(db, streamlit_id, path)

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_file_invalid_path(streamlit_id: uuid.UUID) -> None:
    db = _async_db()

    with pytest.raises(ValueError):
        await FileService().save_file(db, streamlit_id, "../bad.py", "x")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_delete_file_invalid_path(streamlit_id: uuid.UUID) -> None:
    db = _async_db()

    with pytest.raises(ValueError):
        await FileService().delete_file(db, streamlit_id, "bad.exe")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_existing_file_refreshes_is_entrypoint(
    streamlit_id: uuid.UUID,
) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    existing = _make_file(
        streamlit_id=streamlit_id,
        path="app.py",
        content_text="old",
        content_type="text/x-python",
        is_entrypoint=False,
    )
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    file = await service.save_file(db, streamlit_id, "app.py", "new")

    assert file is existing
    assert file.is_entrypoint is True
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_file_size_limit(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings())
    db = _async_db()

    with pytest.raises(ValueError, match="exceeds limit"):
        await service.save_file(
            db, streamlit_id, "big.py", "x" * (MAX_FILE_SIZE_BYTES + 1)
        )

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_requirements_txt_size_limit(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()

    # requirements.txt over 1 MB is rejected.
    with pytest.raises(ValueError, match="exceeds limit"):
        await service.save_file(
            db,
            streamlit_id,
            "requirements.txt",
            "x" * (MAX_REQUIREMENTS_SIZE + 1),
        )
    db.execute.assert_not_called()

    # Other files can still reach the 5 MB limit.
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]
    file = await service.save_file(
        db, streamlit_id, "big.py", "x" * MAX_FILE_SIZE_BYTES
    )
    assert file.path == "big.py"
    assert len(file.content_text) == MAX_FILE_SIZE_BYTES


@pytest.mark.asyncio
async def test_save_file_count_limit(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=1))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(1),
    ]

    with pytest.raises(ValueError, match="File limit exceeded"):
        await service.save_file(db, streamlit_id, "extra.py", "x")

    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_get_entrypoint_content_text(streamlit_id: uuid.UUID) -> None:
    existing = _make_file(streamlit_id=streamlit_id, path="app.py", content_text="text")
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    result = await FileService().get_entrypoint_content(db, streamlit_id)

    assert result == "text"


@pytest.mark.asyncio
async def test_get_entrypoint_content_bytes(streamlit_id: uuid.UUID) -> None:
    existing = _make_file(
        streamlit_id=streamlit_id,
        path="app.py",
        content_text=None,
        content_bytes=b"bytes text",
    )
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    result = await FileService().get_entrypoint_content(db, streamlit_id)

    assert result == "bytes text"


@pytest.mark.asyncio
async def test_get_entrypoint_content_not_found(streamlit_id: uuid.UUID) -> None:
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(None)

    result = await FileService().get_entrypoint_content(db, streamlit_id)

    assert result is None


@pytest.mark.parametrize(
    "path",
    [
        ".streamlit/config.toml",
        "data/file.csv",
        ".env",
        ".hidden.py",
    ],
)
@pytest.mark.asyncio
async def test_save_file_allows_dots_and_hidden(
    streamlit_id: uuid.UUID, path: str
) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]

    file = await service.save_file(db, streamlit_id, path, "content")

    assert file.path == path
    assert file.content_text == "content"
    db.add.assert_called_once_with(file)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_file_size_limit_bytes(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings())
    db = _async_db()

    with pytest.raises(ValueError, match="exceeds limit"):
        await service.save_file(
            db, streamlit_id, "big.png", b"x" * (MAX_FILE_SIZE_BYTES + 1)
        )

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_file_invalid_content_type(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()

    with pytest.raises(ValueError, match="Invalid content_type"):
        await service.save_file(
            db, streamlit_id, "app.py", "print('hi')", content_type="not-a-mime-type"
        )

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_file_app_py_bytes_rejected(streamlit_id: uuid.UUID) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()

    with pytest.raises(ValueError, match="app.py must be uploaded as UTF-8 text"):
        await service.save_file(db, streamlit_id, "app.py", b"\x89PNG")

    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_entrypoint_content_bytes_undecodable(
    streamlit_id: uuid.UUID,
) -> None:
    existing = _make_file(
        streamlit_id=streamlit_id,
        path="app.py",
        content_text=None,
        content_bytes=b"\xff\xfe",
    )
    db = _async_db()
    db.execute.return_value = _make_scalar_one_or_none(existing)

    result = await FileService().get_entrypoint_content(db, streamlit_id)

    assert result is None


@pytest.mark.asyncio
async def test_save_file_normalizes_path_to_lowercase(
    streamlit_id: uuid.UUID,
) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]

    file = await service.save_file(
        db,
        streamlit_id,
        "README.MD",
        "# readme",
        content_type="text/markdown",
    )

    assert file.path == "readme.md"
    assert file.is_entrypoint is False


@pytest.mark.asyncio
async def test_save_file_strips_content_type_parameters(
    streamlit_id: uuid.UUID,
) -> None:
    service = FileService(settings=Settings(MAX_FILES_PER_STREAMLIT=5))
    db = _async_db()
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
    ]

    file = await service.save_file(
        db,
        streamlit_id,
        "note.txt",
        "hello",
        content_type="text/plain; charset=utf-8",
    )

    assert file.content_type == "text/plain"


@pytest.mark.asyncio
async def test_custom_settings_override_size_limits(
    streamlit_id: uuid.UUID,
) -> None:
    service = FileService(
        settings=Settings(
            MAX_FILES_PER_STREAMLIT=5,
            MAX_FILE_SIZE_BYTES=10,
            MAX_REQUIREMENTS_SIZE=5,
        )
    )

    db = _async_db()

    # Other files use the custom MAX_FILE_SIZE_BYTES limit.
    with pytest.raises(ValueError, match="exceeds limit"):
        await service.save_file(db, streamlit_id, "big.py", "x" * 11)

    # requirements.txt uses the custom MAX_REQUIREMENTS_SIZE limit.
    with pytest.raises(ValueError, match="exceeds limit"):
        await service.save_file(db, streamlit_id, "requirements.txt", "x" * 6)

    # At-limit sizes are accepted.
    db.execute.side_effect = [
        _make_scalar_one_or_none(None),
        _make_scalar_one(0),
        _make_scalar_one_or_none(None),
        _make_scalar_one(1),
    ]
    app_file = await service.save_file(db, streamlit_id, "app.py", "x" * 10)
    assert app_file.path == "app.py"

    req_file = await service.save_file(db, streamlit_id, "requirements.txt", "x" * 5)
    assert req_file.path == "requirements.txt"


@pytest.mark.asyncio
async def test_save_file_size_limit_logs_warning(
    streamlit_id: uuid.UUID, caplog: pytest.LogCaptureFixture
) -> None:
    service = FileService(
        settings=Settings(MAX_FILES_PER_STREAMLIT=5, MAX_FILE_SIZE_BYTES=10)
    )
    db = _async_db()

    with caplog.at_level(logging.WARNING, logger="app.services.file_service"):
        with pytest.raises(ValueError, match="exceeds limit"):
            await service.save_file(db, streamlit_id, "big.py", "x" * 11)

    assert "File size limit exceeded" in caplog.text
