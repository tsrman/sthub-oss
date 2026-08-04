"""Code linting service."""

import asyncio
import json
import subprocess
import re

from app.config import get_settings


class LintService:
    """Provides Python code linting and package white-list validation."""

    @staticmethod
    def _run_ruff(code: str) -> subprocess.CompletedProcess:
        """Run ruff on the given code (blocking — call via asyncio.to_thread)."""
        return subprocess.run(
            [
                "ruff",
                "check",
                "--stdin-filename",
                "app.py",
                "--output-format=json",
                "-",
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )

    async def check_syntax(self, code: str) -> list[dict]:
        """Run ruff on the given code and return a list of violation dicts.

        Each dict has keys: line, column, severity, message, code.
        Returns an empty list if ruff is not installed, times out, or produces
        unparseable output. The blocking subprocess runs in a worker thread so
        the event loop stays responsive.
        """
        try:
            result = await asyncio.to_thread(self._run_ruff, code)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode not in (0, 1):
            return []
        try:
            findings = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            return []
        issues: list[dict] = []
        for finding in findings:
            location = finding.get("location", {})
            _end_location = finding.get("end_location", {})
            issues.append(
                {
                    "line": location.get("row", 0),
                    "column": location.get("column", 0),
                    "severity": self._map_severity(
                        finding.get("category", ""), finding.get("fix", {})
                    ),
                    "message": finding.get("message", ""),
                    "code": finding.get("code", ""),
                }
            )
        return issues

    @staticmethod
    def _map_severity(category: str, fix_info: dict) -> str:
        """Map ruff category/fix information to a human-friendly severity."""
        # Most ruff violations are warnings or errors; treat as error by default
        return "error"

    def validate_requirements(self, requirements_text: str) -> tuple[bool, list[str]]:
        """Validate package names against the allowed-packages white-list.

        Parses comma or newline separated requirement strings, strips versions,
        normalises names (lowercase, ``-`` and ``_`` → ``-``), and checks each
        against :data:`settings.allowed_packages_set`.

        Returns ``(is_valid, list_of_unknown_packages)``.
        """
        if not requirements_text or not requirements_text.strip():
            return (True, [])

        settings = get_settings()
        allowed = settings.allowed_packages_set
        unknown: list[str] = []

        # Split on commas and/or newlines
        raw_names = re.split(r"[,\n]+", requirements_text)

        for raw in raw_names:
            raw = raw.strip()
            if not raw:
                continue
            # Strip version specifiers (e.g. pandas==1.5, requests>=2.0)
            name = re.split(r"[>=<!\[]", raw, maxsplit=1)[0].strip()
            # Normalise: lowercase, replace underscores with hyphens
            name = re.sub(r"[-_]+", "-", name).lower()
            if name and name not in allowed:
                unknown.append(name)

        return (len(unknown) == 0, unknown)
