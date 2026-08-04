import uuid
from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.validation import (
    MAX_CODE_SIZE,
    MAX_FILE_SIZE_BYTES,
    MAX_REQUIREMENTS_SIZE,
)
from app.schemas.ai import ChatMessage, ChatRequest
from app.schemas.base import ErrorDetail, ErrorResponse, IdStr
from app.schemas.history import DeploymentListResponse, HistoryEvent
from app.schemas.legacy import LegacyStreamlitCreate, LegacyStreamlitUpdate
from app.schemas.lint import LintRequest, LintResponse
from app.schemas.log import LogLine, LogListResponse
from app.schemas.problem import Problem
from app.schemas.streamlit import (
    RunResponse,
    SlugCheckResponse,
    StreamlitCreate,
    StreamlitDetail,
    StreamlitListResponse,
    StreamlitOwner,
    StreamlitSummary,
    StreamlitUpdate,
)
from app.schemas.streamlit_file import (
    StreamlitFileCreate,
    StreamlitFileListResponse,
    StreamlitFileMetadata,
    StreamlitFileRead,
    StreamlitFileSummary,
    StreamlitFileUpdate,
)
from app.schemas.template import Template, TemplateListResponse
from app.schemas.user import UserResponse


class _DummyOwner:
    def __init__(self, login: str, username: str):
        self.login = login
        self.username = username


class _DummyApp:
    def __init__(self):
        self.id = uuid.uuid4()
        self.name = "Demo application"
        self.slug = "demo-app"
        self.description = "A sample Streamlit application."
        self.status = "running"
        self.cpu_limit = 2.0
        self.memory_limit_mb = 4096
        self.python_version = "3.11"
        self.version = 14
        self.created_at = datetime(2026, 1, 20, 8, 0, 0, tzinfo=timezone.utc)
        self.updated_at = datetime(2026, 6, 23, 7, 52, 0, tzinfo=timezone.utc)
        self.owner = _DummyOwner("demo-user", "Demo user")

    @property
    def url_path(self) -> str:
        return f"/st/{self.owner.login}/{self.slug}"

    @property
    def public_url(self) -> str:
        return f"https://apps.example.com{self.url_path}"


def test_streamlit_create_validates_slug():
    payload = {
        "name": "KPI dashboard",
        "slug": "My App",
        "python_version": "3.11",
        "cpu_limit": 1,
        "memory_limit_mb": 2048,
    }
    created = StreamlitCreate.model_validate(payload)
    assert created.slug == "my-app"


def test_streamlit_create_rejects_invalid_slug():
    with pytest.raises(ValidationError):
        StreamlitCreate.model_validate({"name": "x", "slug": "!"})


def test_streamlit_create_uses_sensible_defaults():
    created = StreamlitCreate.model_validate({"name": "KPI dashboard", "slug": "kpi"})
    assert created.python_version == "3.11"
    assert created.cpu_limit == 1.0
    assert created.memory_limit_mb == 512
    assert created.description is None


def test_streamlit_summary_serializes_with_contract_field_names():
    summary = StreamlitSummary.model_validate(_DummyApp())
    data = summary.model_dump(by_alias=True)

    assert data["cpu_limit"] == 2.0
    assert data["memory_limit_mb"] == 4096
    assert data["python_version"] == "3.11"
    assert data["url"] == "/st/demo-user/demo-app"
    assert data["public_url"] == "https://apps.example.com/st/demo-user/demo-app"
    assert data["owner"] == {
        "login": "demo-user",
        "display_name": "Demo user",
    }


def test_streamlit_summary_rejects_invalid_status():
    with pytest.raises(ValidationError):
        StreamlitSummary(
            id=str(uuid.uuid4()),
            name="App",
            slug="app",
            description=None,
            status="paused",
            cpu_limit=1.0,
            memory_limit_mb=1024,
            python_version="3.11",
            url="/st/u/app",
            public_url="https://apps.example.com/st/u/app",
            version=1,
            owner=StreamlitOwner(login="u", display_name="User"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


def test_streamlit_update_partial_defaults_none():
    update = StreamlitUpdate(name="New name")
    assert update.name == "New name"
    assert update.slug is None
    assert update.description is None
    assert update.python_version is None
    assert update.cpu_limit is None
    assert update.memory_limit_mb is None


def test_streamlit_update_accepts_explicit_null_for_any_field():
    update = StreamlitUpdate.model_validate(
        {
            "name": None,
            "slug": None,
            "description": None,
            "python_version": None,
            "cpu_limit": None,
            "memory_limit_mb": None,
        }
    )
    assert update.name is None
    assert update.slug is None
    assert update.description is None
    assert update.python_version is None
    assert update.cpu_limit is None
    assert update.memory_limit_mb is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("python_version", "3.9"),
        ("cpu_limit", 0.05),
        ("cpu_limit", 5.0),
        ("memory_limit_mb", 32),
        ("memory_limit_mb", 5000),
    ],
)
def test_streamlit_create_rejects_invalid_resource_values(field, value):
    payload = {"name": "App", "slug": "app", field: value}
    with pytest.raises(ValidationError):
        StreamlitCreate.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("python_version", "3.9"),
        ("cpu_limit", 0.05),
        ("cpu_limit", 5.0),
        ("memory_limit_mb", 32),
        ("memory_limit_mb", 5000),
    ],
)
def test_streamlit_update_rejects_invalid_resource_values(field, value):
    payload = {field: value}
    with pytest.raises(ValidationError):
        StreamlitUpdate.model_validate(payload)


def test_streamlit_detail_runtime_fields_default_to_none():
    detail = StreamlitDetail(
        id=str(uuid.uuid4()),
        name="App",
        slug="app",
        description=None,
        status="stopped",
        cpu_limit=1.0,
        memory_limit_mb=1024,
        python_version="3.11",
        url="/st/u/app",
        public_url="https://apps.example.com/st/u/app",
        version=1,
        owner=StreamlitOwner(login="u", display_name="User"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert detail.container_id is None
    assert detail.image_tag is None


class _DummyUser:
    def __init__(self):
        self.login = "demo-user"
        self.username = "Demo user"
        self.email = "user@example.com"
        self.group = "data-scientists"


def test_user_response_serializes_only_contract_fields():
    user = UserResponse.model_validate(
        {
            "login": "demo-user",
            "username": "Demo user",
            "email": "user@example.com",
            "group": "data-scientists",
        }
    )
    data = user.model_dump(by_alias=True)
    assert set(data.keys()) == {"login", "display_name", "email", "group", "is_admin"}
    assert data["login"] == "demo-user"
    assert data["is_admin"] is False
    assert data["display_name"] == "Demo user"
    assert data["email"] == "user@example.com"
    assert data["group"] == "data-scientists"


def test_id_str_converts_uuid_to_string():
    ta = TypeAdapter(IdStr)
    uid = uuid.uuid4()
    assert ta.validate_python(uid) == str(uid)
    assert ta.validate_python(str(uid)) == str(uid)


def test_id_str_rejects_none_and_int():
    ta = TypeAdapter(IdStr)
    with pytest.raises(ValidationError):
        ta.validate_python(None)
    with pytest.raises(ValidationError):
        ta.validate_python(123)


class _DummyFile:
    def __init__(self):
        self.id = uuid.uuid4()
        self.path = "app.py"
        self.content_type = "text/x-python"
        self.is_entrypoint = True
        self.updated_at = datetime(2026, 6, 23, 7, 52, 0, tzinfo=timezone.utc)


def test_streamlit_file_summary_serializes():
    file = _DummyFile()
    summary = StreamlitFileSummary.model_validate(file)
    data = summary.model_dump(by_alias=True)

    assert set(data.keys()) == {
        "id",
        "path",
        "content_type",
        "is_entrypoint",
        "updated_at",
    }
    assert data["id"] == str(file.id)
    assert data["path"] == "app.py"
    assert data["content_type"] == "text/x-python"
    assert data["is_entrypoint"] is True
    assert data["updated_at"] == file.updated_at


def test_streamlit_file_metadata_smoke():
    meta = StreamlitFileMetadata(
        id=str(uuid.uuid4()),
        path="app.py",
        content_type="text/x-python",
        is_entrypoint=True,
    )
    assert meta.path == "app.py"
    assert meta.is_entrypoint is True


def test_problem_smoke():
    problem = Problem(line=21, column=14, severity="error", message="Missing colon")
    assert problem.line == 21
    assert problem.column == 14
    assert problem.severity == "error"
    assert problem.message == "Missing colon"


def test_problem_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        Problem(line=1, column=1, severity="info", message="x")


def test_lint_request_smoke():
    request = LintRequest(code="import streamlit as st")
    assert request.code == "import streamlit as st"


def test_lint_request_code_rejects_oversized_input():
    with pytest.raises(ValidationError):
        LintRequest(code="x" * (MAX_CODE_SIZE + 1))


# ---------------------------------------------------------------------------
# AI chat schemas
# ---------------------------------------------------------------------------


def test_chat_request_allows_up_to_40_messages():
    messages = [ChatMessage(role="user", content="hi")] * 40
    assert len(ChatRequest(messages=messages).messages) == 40


def test_chat_request_rejects_41_messages():
    messages = [ChatMessage(role="user", content="hi")] * 41
    with pytest.raises(ValidationError):
        ChatRequest(messages=messages)


def test_chat_message_allows_20000_chars():
    assert len(ChatMessage(role="user", content="x" * 20000).content) == 20000


def test_chat_message_rejects_oversized_content():
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="x" * 20001)


def test_lint_response_is_exported_from_app_schemas():
    from app.schemas import LintResponse as ExportedLintResponse

    assert ExportedLintResponse is LintResponse


def test_lint_response_smoke():
    response = LintResponse(ok=True, problems=[])
    assert response.ok is True
    assert response.problems == []


def test_lint_response_with_problems():
    response = LintResponse(
        ok=False,
        problems=[Problem(line=1, column=2, severity="warning", message="x")],
    )
    assert response.ok is False
    assert len(response.problems) == 1


def test_lint_response_default_empty_problems():
    response = LintResponse(ok=True)
    assert response.problems == []


def test_log_line_smoke():
    line = LogLine(
        ts=datetime(2026, 6, 23, 9, 52, 14, tzinfo=timezone.utc),
        level="INFO",
        source="streamlit",
        message="GET / 200 OK 14ms",
    )
    assert line.level == "INFO"
    assert line.source == "streamlit"


class _DummyLog:
    def __init__(self):
        self.ts = datetime(2026, 6, 23, 9, 52, 14, tzinfo=timezone.utc)
        self.level = "INFO"
        self.stage = "worker"
        self.message = "build done"


def test_log_line_maps_stage_alias_to_source():
    line = LogLine.model_validate(_DummyLog())
    assert line.source == "worker"
    data = line.model_dump(by_alias=True)
    assert data["source"] == "worker"

    line_from_dict = LogLine.model_validate(
        {
            "ts": datetime(2026, 6, 23, 9, 52, 14, tzinfo=timezone.utc),
            "level": "INFO",
            "stage": "build",
            "message": "x",
        }
    )
    assert line_from_dict.source == "build"


def test_run_response_id_is_str():
    response = RunResponse(id="kpi-shop", status="building", version=22)
    assert response.id == "kpi-shop"


def test_streamlit_list_response_smoke():
    response = StreamlitListResponse(items=[], total=0, running=0)
    assert response.total == 0
    assert response.running == 0


def test_slug_check_response_smoke():
    response = SlugCheckResponse(
        slug="kpi-shop",
        available=True,
        url="/st/u/kpi-shop",
    )
    assert response.slug == "kpi-shop"
    assert response.normalized == "kpi-shop"
    assert response.available is True


def test_slug_check_response_preserves_input_slug_and_normalizes():
    response = SlugCheckResponse(
        slug="My App",
        available=True,
        url="/st/u/my-app",
    )
    assert response.slug == "My App"
    assert response.normalized == "my-app"


def test_slug_check_response_computes_normalized_regardless_of_input():
    response = SlugCheckResponse(
        slug="My App",
        available=True,
        normalized="ignored",
        url="/st/u/my-app",
    )
    assert response.slug == "My App"
    assert response.normalized == "my-app"


def test_slug_check_response_url_must_match_login_and_slug():
    response = SlugCheckResponse.model_validate(
        {
            "slug": "My App",
            "available": True,
            "url": "/st/u/my-app",
        },
        context={"login": "u"},
    )
    assert response.url == "/st/u/my-app"

    with pytest.raises(ValidationError):
        SlugCheckResponse.model_validate(
            {
                "slug": "my-app",
                "available": True,
                "url": "/st/u/other-app",
            },
            context={"login": "u"},
        )


@pytest.mark.parametrize(
    "url",
    [
        "/bad/my-app",
        "/st/u/other-app",
        "/st/u/my-app/extra",
    ],
)
def test_slug_check_response_rejects_invalid_url_without_login(url):
    with pytest.raises(ValidationError):
        SlugCheckResponse(
            slug="my-app",
            available=True,
            url=url,
        )


def test_history_event_smoke():
    event = HistoryEvent(
        id="evt-1029",
        ts=datetime(2026, 6, 23, 9, 52, 14, tzinfo=timezone.utc),
        streamlit_id="demo-app",
        streamlit_name="Demo application",
        url="/st/demo-user/demo-app",
        kind="deploy",
        action="Deployed",
        version=14,
        actor=StreamlitOwner(login="demo-user", display_name="Demo user"),
        result="ok",
    )
    assert event.result == "ok"


def test_history_event_accepts_uuid_ids_as_strings():
    event_id = uuid.uuid4()
    streamlit_id = uuid.uuid4()
    event = HistoryEvent(
        id=event_id,
        ts=datetime(2026, 6, 23, 9, 52, 14, tzinfo=timezone.utc),
        streamlit_id=streamlit_id,
        streamlit_name="Demo application",
        url="/st/demo-user/demo-app",
        kind="deploy",
        action="Deployed",
        version=14,
        actor=StreamlitOwner(login="demo-user", display_name="Demo user"),
        result="ok",
    )
    assert event.id == str(event_id)
    assert event.streamlit_id == str(streamlit_id)


def test_template_smoke():
    template = Template(
        id="kpi",
        name="KPI dashboard",
        code="import streamlit as st",
        requirements="streamlit==1.36.0",
    )
    assert template.badge is None
    assert template.tags == []


def test_template_strips_name():
    template = Template(
        id="kpi",
        name="  KPI dashboard  ",
        code="import streamlit as st",
        requirements="streamlit==1.36.0",
    )
    assert template.name == "KPI dashboard"


def test_template_rejects_whitespace_name():
    with pytest.raises(ValidationError):
        Template(
            id="kpi",
            name="   ",
            code="import streamlit as st",
            requirements="streamlit==1.36.0",
        )


def test_streamlit_file_list_response_smoke():
    response = StreamlitFileListResponse(items=[], total=0)
    assert response.total == 0


def test_streamlit_summary_rejects_missing_resource_fields():
    base = {
        "id": str(uuid.uuid4()),
        "name": "App",
        "slug": "app",
        "status": "stopped",
        "cpu_limit": 1.0,
        "memory_limit_mb": 1024,
        "python_version": "3.11",
        "url": "/st/u/app",
        "public_url": "https://apps.example.com/st/u/app",
        "version": 1,
        "owner": {"login": "u", "display_name": "User"},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for field in ("cpu_limit", "memory_limit_mb", "python_version"):
        payload = {k: v for k, v in base.items() if k != field}
        with pytest.raises(ValidationError):
            StreamlitSummary.model_validate(payload)


def test_problem_line_col_must_be_positive():
    with pytest.raises(ValidationError):
        Problem(line=0, col=1, severity="error", message="x")
    with pytest.raises(ValidationError):
        Problem(line=1, col=0, severity="error", message="x")


def test_log_list_response_smoke():
    response = LogListResponse(items=[], next_since=None)
    assert response.items == []
    assert response.next_since is None


def test_deployment_list_response_smoke():
    response = DeploymentListResponse(items=[], total=0, next_cursor=None)
    assert response.total == 0
    assert response.next_cursor is None


def test_template_list_response_smoke():
    response = TemplateListResponse(items=[])
    assert response.items == []


def test_error_response_smoke():
    response = ErrorResponse(
        error={"code": "validation_error", "message": "Invalid input"}
    )
    assert response.error.code == "validation_error"
    assert response.error.message == "Invalid input"
    assert response.error.details is None


def test_error_response_with_details():
    response = ErrorResponse(
        error={
            "code": "field_error",
            "message": "Bad field",
            "details": {"field": "slug"},
        }
    )
    assert response.error.code == "field_error"
    assert response.error.details == {"field": "slug"}


def test_log_line_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        LogLine(
            ts=datetime(2026, 6, 23, 9, 52, 14),
            level="INFO",
            source="streamlit",
            message="x",
        )


def test_history_event_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        HistoryEvent(
            id="evt-1",
            ts=datetime(2026, 6, 23, 9, 52, 14),
            streamlit_id="app",
            streamlit_name="App",
            url="/st/u/app",
            kind="deploy",
            action="deploy",
            version=1,
            actor=StreamlitOwner(login="u", display_name="User"),
            result="ok",
        )


def test_streamlit_summary_rejects_naive_datetime():
    base = {
        "id": str(uuid.uuid4()),
        "name": "App",
        "slug": "app",
        "status": "stopped",
        "cpu_limit": 1.0,
        "memory_limit_mb": 1024,
        "python_version": "3.11",
        "url": "/st/u/app",
        "public_url": "https://apps.example.com/st/u/app",
        "version": 1,
        "owner": {"login": "u", "display_name": "User"},
    }
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(
            {
                **base,
                "created_at": datetime(2026, 1, 1),
                "updated_at": datetime.now(timezone.utc),
            }
        )
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(
            {
                **base,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime(2026, 1, 1),
            }
        )


def test_streamlit_file_summary_rejects_naive_datetime():
    file = _DummyFile()
    file.updated_at = datetime(2026, 6, 23, 7, 52, 14)
    with pytest.raises(ValidationError):
        StreamlitFileSummary.model_validate(file)


def test_streamlit_file_create_content_max_length():
    with pytest.raises(ValidationError):
        StreamlitFileCreate(content="x" * (MAX_FILE_SIZE_BYTES + 1))


def test_streamlit_file_update_content_max_length():
    with pytest.raises(ValidationError):
        StreamlitFileUpdate(content="x" * (MAX_FILE_SIZE_BYTES + 1))


def test_streamlit_file_read_content_max_length():
    with pytest.raises(ValidationError):
        StreamlitFileRead(
            id=str(uuid.uuid4()),
            path="app.py",
            content_type="text/x-python",
            is_entrypoint=True,
            content="x" * (MAX_FILE_SIZE_BYTES + 1),
            updated_at=datetime.now(timezone.utc),
        )


def test_template_code_max_length():
    with pytest.raises(ValidationError):
        Template(id="x", name="X", code="x" * (MAX_CODE_SIZE + 1), requirements="")


def test_template_requirements_max_length():
    with pytest.raises(ValidationError):
        Template(
            id="x",
            name="X",
            code="import streamlit as st",
            requirements="x" * (MAX_REQUIREMENTS_SIZE + 1),
        )


def test_run_response_version_optional():
    response = RunResponse(id="app", status="stopped")
    assert response.version is None


def test_streamlit_file_read_smoke():
    file = StreamlitFileRead(
        id=str(uuid.uuid4()),
        path="app.py",
        content_type="text/x-python",
        is_entrypoint=True,
        content="import streamlit as st",
        updated_at=datetime.now(timezone.utc),
    )
    assert file.path == "app.py"
    assert file.content == "import streamlit as st"


def test_streamlit_update_slug_non_string_raises_value_error():
    with pytest.raises(ValidationError):
        StreamlitUpdate.model_validate({"slug": 123})


def test_streamlit_create_slug_non_string_raises_value_error():
    with pytest.raises(ValidationError):
        StreamlitCreate.model_validate({"name": "x", "slug": 123})


def _streamlit_summary_base():
    return {
        "id": str(uuid.uuid4()),
        "slug": "app",
        "status": "stopped",
        "cpu_limit": 1.0,
        "memory_limit_mb": 1024,
        "python_version": "3.11",
        "url": "/st/u/app",
        "public_url": "https://apps.example.com/st/u/app",
        "version": 1,
        "owner": {"login": "u", "display_name": "User"},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.parametrize("name", ["", "x" * 101, "   "])
def test_streamlit_summary_rejects_invalid_name(name):
    payload = {**_streamlit_summary_base(), "name": name}
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(payload)


@pytest.mark.parametrize("slug", ["", "x" * 41, "!"])
def test_streamlit_summary_rejects_invalid_slug(slug):
    payload = {**_streamlit_summary_base(), "slug": slug}
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(payload)


@pytest.mark.parametrize("login", ["", "!user", "x" * 41])
def test_streamlit_summary_rejects_invalid_owner_login(login):
    payload = {
        **_streamlit_summary_base(),
        "owner": {"login": login, "display_name": "User"},
    }
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(payload)


def test_streamlit_summary_rejects_negative_version():
    payload = {**_streamlit_summary_base(), "version": -1}
    with pytest.raises(ValidationError):
        StreamlitSummary.model_validate(payload)


@pytest.mark.parametrize("login", ["", "!user", "x" * 41, 123])
def test_user_response_rejects_invalid_login(login):
    with pytest.raises(ValidationError):
        UserResponse(
            login=login,
            display_name="User",
            email="user@example.com",
            group="data-scientists",
        )


def test_legacy_streamlit_create_strips_name():
    created = LegacyStreamlitCreate.model_validate(
        {"name": "  Legacy App  ", "slug": "legacy"}
    )
    assert created.name == "Legacy App"


def test_legacy_streamlit_create_rejects_empty_name():
    with pytest.raises(ValidationError):
        LegacyStreamlitCreate.model_validate({"name": "   ", "slug": "legacy"})


def test_legacy_streamlit_update_strips_name():
    updated = LegacyStreamlitUpdate.model_validate({"name": "  Legacy App  "})
    assert updated.name == "Legacy App"
    assert updated.slug is None


def test_legacy_streamlit_update_rejects_empty_name():
    with pytest.raises(ValidationError):
        LegacyStreamlitUpdate.model_validate({"name": "   "})


def test_legacy_streamlit_create_code_max_length():
    with pytest.raises(ValidationError):
        LegacyStreamlitCreate.model_validate(
            {"name": "App", "slug": "app", "code": "x" * (MAX_CODE_SIZE + 1)}
        )


def test_legacy_streamlit_create_requirements_max_length():
    with pytest.raises(ValidationError):
        LegacyStreamlitCreate.model_validate(
            {
                "name": "App",
                "slug": "app",
                "requirements": "x" * (MAX_REQUIREMENTS_SIZE + 1),
            }
        )


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_template_rejects_invalid_name(name):
    with pytest.raises(ValidationError):
        Template(id="x", name=name, code="import streamlit as st", requirements="")


def test_description_accepts_max_length_boundary():
    created = StreamlitCreate.model_validate(
        {"name": "App", "slug": "app", "description": "x" * 5000}
    )
    assert created.description == "x" * 5000


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StreamlitCreate.model_validate(
            {"name": "App", "slug": "app", "description": "x" * 5001}
        ),
        lambda: StreamlitUpdate.model_validate({"description": "x" * 5001}),
        lambda: StreamlitSummary.model_validate(
            {**_streamlit_summary_base(), "description": "x" * 5001}
        ),
        lambda: Template(
            id="x",
            name="X",
            code="import streamlit as st",
            requirements="",
            description="x" * 5001,
        ),
    ],
)
def test_description_rejects_over_max_length(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (StreamlitCreate, {"name": "App", "slug": "app"}),
        (StreamlitUpdate, {"name": "App"}),
        (LintRequest, {"code": "x = 1"}),
        (StreamlitFileCreate, {"content": "x = 1"}),
        (StreamlitFileUpdate, {"content": "x = 1"}),
    ],
)
def test_request_schemas_reject_extra_fields(schema, kwargs):
    with pytest.raises(ValidationError):
        schema.model_validate({**kwargs, "unexpected": "value"})


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (
            StreamlitSummary,
            {
                **_streamlit_summary_base(),
                "name": "App",
            },
        ),
        (
            StreamlitDetail,
            {
                **_streamlit_summary_base(),
                "name": "App",
                "container_id": None,
                "image_tag": None,
            },
        ),
        (
            StreamlitOwner,
            {"login": "u", "display_name": "User"},
        ),
        (
            StreamlitListResponse,
            {"items": [], "total": 0, "running": 0},
        ),
        (
            RunResponse,
            {"id": "app", "status": "stopped"},
        ),
        (
            SlugCheckResponse,
            {"slug": "app", "available": True, "url": "/st/u/app"},
        ),
        (
            UserResponse,
            {
                "login": "u",
                "display_name": "User",
                "email": "user@example.com",
                "group": "data-scientists",
            },
        ),
        (
            LogLine,
            {
                "ts": datetime.now(timezone.utc),
                "level": "INFO",
                "source": "streamlit",
                "message": "x",
            },
        ),
        (LogListResponse, {"items": [], "next_since": None}),
        (
            HistoryEvent,
            {
                "id": "evt-1",
                "ts": datetime.now(timezone.utc),
                "streamlit_id": "app",
                "streamlit_name": "App",
                "url": "/st/u/app",
                "kind": "deploy",
                "action": "deploy",
                "version": 1,
                "actor": {"login": "u", "display_name": "User"},
                "result": "ok",
            },
        ),
        (DeploymentListResponse, {"items": [], "total": 0, "next_cursor": None}),
        (
            Template,
            {
                "id": "x",
                "name": "X",
                "code": "import streamlit as st",
                "requirements": "",
            },
        ),
        (TemplateListResponse, {"items": []}),
        (Problem, {"line": 1, "col": 1, "severity": "error", "message": "x"}),
        (
            StreamlitFileRead,
            {
                "id": str(uuid.uuid4()),
                "path": "app.py",
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "content": "import streamlit as st",
                "updated_at": datetime.now(timezone.utc),
            },
        ),
        (
            StreamlitFileSummary,
            {
                "id": str(uuid.uuid4()),
                "path": "app.py",
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "updated_at": datetime.now(timezone.utc),
            },
        ),
        (
            StreamlitFileMetadata,
            {
                "id": str(uuid.uuid4()),
                "path": "app.py",
                "content_type": "text/x-python",
                "is_entrypoint": True,
            },
        ),
        (StreamlitFileListResponse, {"items": [], "total": 0}),
        (LintResponse, {"ok": True, "problems": []}),
        (ErrorResponse, {"error": {"code": "x", "message": "m"}}),
        (ErrorDetail, {"code": "x", "message": "m"}),
    ],
)
def test_response_schemas_reject_extra_fields(schema, kwargs):
    with pytest.raises(ValidationError):
        schema.model_validate({**kwargs, "unexpected": "value"})


def test_streamlit_update_normalizes_slug():
    update = StreamlitUpdate.model_validate({"slug": "My App"})
    assert update.slug == "my-app"


def test_streamlit_update_rejects_invalid_slug():
    with pytest.raises(ValidationError):
        StreamlitUpdate.model_validate({"slug": "!"})


@pytest.mark.parametrize(
    "schema, kwargs, path",
    [
        (
            StreamlitFileSummary,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "updated_at": datetime.now(timezone.utc),
            },
            "app.py",
        ),
        (
            StreamlitFileMetadata,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
            },
            "app.py",
        ),
        (
            StreamlitFileRead,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "content": "import streamlit as st",
                "updated_at": datetime.now(timezone.utc),
            },
            "app.py",
        ),
    ],
)
def test_streamlit_file_path_validation_accepts_valid_path(schema, kwargs, path):
    file = schema.model_validate({**kwargs, "path": path})
    assert file.path == path


@pytest.mark.parametrize(
    "schema, kwargs, path",
    [
        (
            StreamlitFileSummary,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "updated_at": datetime.now(timezone.utc),
            },
            "//app.py",
        ),
        (
            StreamlitFileMetadata,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
            },
            "app.exe",
        ),
        (
            StreamlitFileRead,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "content": "import streamlit as st",
                "updated_at": datetime.now(timezone.utc),
            },
            "../app.py",
        ),
        (
            StreamlitFileRead,
            {
                "id": str(uuid.uuid4()),
                "content_type": "text/x-python",
                "is_entrypoint": True,
                "content": "import streamlit as st",
                "updated_at": datetime.now(timezone.utc),
            },
            "/app.py",
        ),
    ],
)
def test_streamlit_file_path_validation_rejects_invalid_path(schema, kwargs, path):
    with pytest.raises(ValidationError):
        schema.model_validate({**kwargs, "path": path})


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (StreamlitCreate, {"name": "  App  ", "slug": "app"}),
        (StreamlitUpdate, {"name": "  App  "}),
    ],
)
def test_streamlit_request_strips_name(schema, kwargs):
    obj = schema.model_validate(kwargs)
    assert obj.name == "App"


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (StreamlitCreate, {"name": "   ", "slug": "app"}),
        (StreamlitUpdate, {"name": "   "}),
    ],
)
def test_streamlit_request_rejects_whitespace_name(schema, kwargs):
    with pytest.raises(ValidationError):
        schema.model_validate(kwargs)


def test_id_str_rejects_empty_string():
    ta = TypeAdapter(IdStr)
    with pytest.raises(ValidationError):
        ta.validate_python("")


def test_streamlit_file_read_requirements_max_size():
    with pytest.raises(ValidationError):
        StreamlitFileRead(
            id=str(uuid.uuid4()),
            path="requirements.txt",
            content_type="text/plain",
            is_entrypoint=False,
            content="x" * (MAX_REQUIREMENTS_SIZE + 1),
            updated_at=datetime.now(timezone.utc),
        )


def test_streamlit_file_create_requirements_max_size_via_context():
    with pytest.raises(ValidationError):
        StreamlitFileCreate.model_validate(
            {"content": "x" * (MAX_REQUIREMENTS_SIZE + 1)},
            context={"path": "requirements.txt"},
        )


def test_streamlit_file_update_requirements_max_size_via_context():
    with pytest.raises(ValidationError):
        StreamlitFileUpdate.model_validate(
            {"content": "x" * (MAX_REQUIREMENTS_SIZE + 1)},
            context={"path": "requirements.txt"},
        )


@pytest.mark.parametrize("schema", [StreamlitFileCreate, StreamlitFileUpdate])
def test_streamlit_file_content_allows_missing_context_path(schema):
    # The API path is not available during request-body validation; the service
    # layer enforces the stricter requirements.txt size limit.
    file = schema.model_validate({"content": "x = 1"})
    assert file.content == "x = 1"


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (StreamlitFileCreate, {"content": "x = 1", "content_type": "not-a-mime-type"}),
        (StreamlitFileUpdate, {"content": "x = 1", "content_type": "not-a-mime-type"}),
        (
            StreamlitFileRead,
            {
                "id": str(uuid.uuid4()),
                "path": "app.py",
                "content_type": "not-a-mime-type",
                "is_entrypoint": True,
                "content": "import streamlit as st",
                "updated_at": datetime.now(timezone.utc),
            },
        ),
    ],
)
def test_streamlit_file_rejects_invalid_content_type(schema, kwargs):
    with pytest.raises(ValidationError):
        schema.model_validate(kwargs)


def test_streamlit_file_read_app_py_allows_size_between_requirements_and_file_limit():
    content = "x" * (MAX_REQUIREMENTS_SIZE + 1)
    file = StreamlitFileRead(
        id=str(uuid.uuid4()),
        path="app.py",
        content_type="text/x-python",
        is_entrypoint=True,
        content=content,
        updated_at=datetime.now(timezone.utc),
    )
    assert file.content == content


@pytest.mark.parametrize(
    "schema, kwargs",
    [
        (StreamlitListResponse, {"items": [], "total": -1, "running": 0}),
        (StreamlitListResponse, {"items": [], "total": 0, "running": -1}),
        (DeploymentListResponse, {"items": [], "total": -1}),
        (StreamlitFileListResponse, {"items": [], "total": -1}),
    ],
)
def test_list_response_rejects_negative_total(schema, kwargs):
    with pytest.raises(ValidationError):
        schema(**kwargs)
