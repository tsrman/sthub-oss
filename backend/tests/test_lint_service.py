"""Unit tests for LintService (syntax checking and requirements validation).

``check_syntax`` shells out to ``ruff`` in a worker thread; we patch
``subprocess.run`` so the parsing logic is exercised deterministically without
depending on ruff being on PATH. ``validate_requirements`` is pure and patches
settings for a known allow-list.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.lint_service import LintService


def _ruff_result(findings: list[dict], returncode: int = 1) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=json.dumps(findings))


# ---------------------------------------------------------------------------
# check_syntax
# ---------------------------------------------------------------------------


async def test_check_syntax_parses_findings() -> None:
    findings = [
        {
            "location": {"row": 3, "column": 5},
            "end_location": {"row": 3, "column": 9},
            "message": "Undefined name `st`",
            "code": "F821",
            "category": "Pyflakes",
            "fix": None,
        }
    ]
    with patch(
        "app.services.lint_service.subprocess.run", return_value=_ruff_result(findings)
    ):
        issues = await LintService().check_syntax("print(st)")

    assert len(issues) == 1
    issue = issues[0]
    assert issue["line"] == 3
    assert issue["column"] == 5
    assert issue["code"] == "F821"
    assert issue["message"] == "Undefined name `st`"
    assert issue["severity"] == "error"


async def test_check_syntax_runs_subprocess_off_the_event_loop() -> None:
    """The blocking ruff call must be delegated to ``asyncio.to_thread``."""
    import asyncio as asyncio_module

    to_thread_calls: list[object] = []
    real_to_thread = asyncio_module.to_thread

    async def spy_to_thread(func, /, *args, **kwargs):
        to_thread_calls.append(func)
        return await real_to_thread(func, *args, **kwargs)

    with (
        patch(
            "app.services.lint_service.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=""),
        ),
        patch("app.services.lint_service.asyncio.to_thread", new=spy_to_thread),
    ):
        issues = await LintService().check_syntax("x = 1\n")

    assert to_thread_calls, "check_syntax must run ruff via asyncio.to_thread"
    assert issues == []


async def test_check_syntax_clean_code_returns_empty() -> None:
    result = SimpleNamespace(returncode=0, stdout="")
    with patch("app.services.lint_service.subprocess.run", return_value=result):
        assert await LintService().check_syntax("x = 1\n") == []


async def test_check_syntax_ruff_crash_returns_empty() -> None:
    # returncode not in (0, 1) means ruff itself failed → no issues surfaced.
    result = SimpleNamespace(returncode=2, stdout="boom")
    with patch("app.services.lint_service.subprocess.run", return_value=result):
        assert await LintService().check_syntax("???") == []


async def test_check_syntax_ruff_missing_returns_empty() -> None:
    with patch(
        "app.services.lint_service.subprocess.run", side_effect=FileNotFoundError
    ):
        assert await LintService().check_syntax("x = 1") == []


async def test_check_syntax_ruff_timeout_returns_empty() -> None:
    with patch(
        "app.services.lint_service.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ruff", timeout=10),
    ):
        assert await LintService().check_syntax("x = 1") == []


async def test_check_syntax_invalid_json_returns_empty() -> None:
    result = SimpleNamespace(returncode=1, stdout="not json")
    with patch("app.services.lint_service.subprocess.run", return_value=result):
        assert await LintService().check_syntax("x = 1") == []


# ---------------------------------------------------------------------------
# Problem schema alignment (regression: API 500 on any lint finding)
# ---------------------------------------------------------------------------


def test_problem_schema_accepts_lint_issue_shape() -> None:
    """The API ``Problem`` schema must accept the dicts produced by check_syntax."""
    from app.schemas.problem import Problem

    issue = {
        "line": 5,
        "column": 12,
        "severity": "error",
        "message": "SyntaxError: invalid syntax",
        "code": "E999",
    }
    problem = Problem(**issue)
    assert problem.column == 12
    assert problem.code == "E999"


async def test_check_syntax_real_ruff_output_matches_problem_schema() -> None:
    """End-to-end: real ruff findings must fit the API ``Problem`` schema."""
    import shutil

    if shutil.which("ruff") is None:
        pytest.skip("ruff binary not on PATH")

    from app.schemas.problem import Problem

    issues = await LintService().check_syntax("def broken(:\n    pass\n")
    assert issues, "ruff must flag the syntax error"
    problems = [Problem(**issue) for issue in issues]
    assert problems[0].line >= 1


# ---------------------------------------------------------------------------
# validate_requirements
# ---------------------------------------------------------------------------


@pytest.fixture
def allowed_packages():
    fake = SimpleNamespace(allowed_packages_set={"streamlit", "pandas", "numpy"})
    with patch("app.services.lint_service.get_settings", return_value=fake):
        yield


def test_validate_requirements_empty_is_valid(allowed_packages) -> None:
    assert LintService().validate_requirements("") == (True, [])
    assert LintService().validate_requirements("   \n  ") == (True, [])


def test_validate_requirements_all_allowed(allowed_packages) -> None:
    ok, unknown = LintService().validate_requirements(
        "streamlit==1.36.0\npandas>=2.0\nnumpy"
    )
    assert ok is True
    assert unknown == []


def test_validate_requirements_flags_unknown(allowed_packages) -> None:
    ok, unknown = LintService().validate_requirements("streamlit\nrequests==2.0\nflask")
    assert ok is False
    assert set(unknown) == {"requests", "flask"}


def test_validate_requirements_normalises_names(allowed_packages) -> None:
    # Underscores and case are normalised before the allow-list check.
    ok, unknown = LintService().validate_requirements("Pandas\nNUMPY")
    assert ok is True
    assert unknown == []


def test_validate_requirements_comma_separated(allowed_packages) -> None:
    ok, unknown = LintService().validate_requirements("streamlit, pandas, scipy")
    assert ok is False
    assert unknown == ["scipy"]
