"""Check an exported STHub tree for private or generated release artifacts."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str
    line: int | None = None


EXCLUDED_PARTS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".review-venv",
    ".venv",
    ".auth",
    "__pycache__",
    "design",
    "node_modules",
    "venv",
}

# Shapes of internal infrastructure, not specific hosts: naming a private domain
# here would publish the very thing this check exists to keep out of the tree.
PRIVATE_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internal .corp host", re.compile(r"\b[a-z0-9][a-z0-9-]*\.corp\b")),
    # Two labels before .local distinguishes an AD/mDNS zone (host.zone.local)
    # from a single-label development name such as the sthub.local sample cert.
    ("internal .local host", re.compile(r"\b[a-z0-9][a-z0-9-]*\.[a-z0-9-]+\.local\b")),
    ("internal .lan host", re.compile(r"\b[a-z0-9][a-z0-9-]*\.lan\b")),
    ("internal PKI path", re.compile(r"/opt/pki/")),
)

# Kept in sync with PUBLIC_REGISTRIES in verify_compose.py. The two scripts are run
# both as modules and as standalone files, so neither imports the other.
_PUBLIC_REGISTRIES = frozenset(
    {
        "docker.io",
        "index.docker.io",
        "quay.io",
        "ghcr.io",
        "gcr.io",
        "mcr.microsoft.com",
        "registry.k8s.io",
    }
)
_DOCKERFILE_FROM = re.compile(
    r"^\s*from\s+(?P<host>[a-z0-9][a-z0-9.-]*(?::\d+)?)/\S", re.IGNORECASE
)

_PATTERN_SOURCE_FILES = frozenset(
    {"scripts/check_release.py", "scripts/tests/test_check_release.py"}
)

# The UI, the API messages and the docs are English. Cyrillic in a source file
# means a string was reintroduced in the project's former language.
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_CYRILLIC_EXEMPT_PREFIXES = ("frontend/public/monaco-editor/",)

_PRIVATE_KEY_HEADER = "-----BEGIN " "PRIVATE KEY-----"  # nosec: not a real key
_SECRET_PLACEHOLDERS = ("test", "fake", "example", "dummy", "placeholder")

REQUIRED_PUBLIC_FILES = {
    "README.md",
    "LICENSE",
    "NOTICE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "THIRD_PARTY_NOTICES.md",
    "third_party/licenses/LGPL-3.0.txt",
    "third_party/licenses/GPL-3.0.txt",
    "third_party/licenses/MPL-2.0.txt",
    "third_party/licenses/CC-BY-4.0.txt",
    "docs/architecture.md",
    "docs/configuration.md",
    "docs/deployment.md",
    "docs/development.md",
    "docs/api-contract.md",
    "docs/assets/dashboard.png",
    "frontend/public/monaco-editor/ThirdPartyNotices.txt",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    "streamlit-base/requirements.txt",
}

_BASE_REQUIREMENTS = "streamlit-base/requirements.txt"
_BASE_DOCKERFILE = "streamlit-base/Dockerfile"
_EXACT_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)==(?P<version>[0-9]+(?:\.[0-9]+)*)$"
)
_SAFE_BASE_MINIMUMS = {
    "streamlit": "1.54.0",
    "requests": "2.33.0",
    "pyarrow": "23.0.1",
    "python-dotenv": "1.2.2",
    "pillow": "12.3.0",
}

_MARKDOWN_LINK = re.compile(
    r"(?P<image>!)?\[[^\]]*\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<bare>[^\s)]+))"
)
_MARKDOWN_REFERENCE_DEFINITION = re.compile(
    r"^\s{0,3}\[(?P<label>[^\]]+)\]:\s*(?:<(?P<angle>[^>]+)>|(?P<bare>[^\s]+))"
)
_REFERENCE_IMAGE = re.compile(
    r"!\[(?P<alt>[^\]]*)\](?:\[(?P<reference>[^\]]*)\])?(?!\()"
)
# Image links to the screenshot skip the link check because it is a binary that
# tooling may regenerate; its presence is enforced via REQUIRED_PUBLIC_FILES.
_DEFERRED_SCREENSHOT = "docs/assets/dashboard.png"


def _paths_from_git(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / name.decode("utf-8") for name in result.stdout.split(b"\0") if name]


def _paths_from_tree(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]


def _is_dependency_license_fixture(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return "license" in parts or "licenses" in parts


def _path_finding(relative: Path) -> str | None:
    parts = relative.parts
    excluded = next((part for part in parts if part in EXCLUDED_PARTS), None)
    if excluded is not None:
        return f"excluded path part: {excluded}"
    if parts[:2] == ("docs", "superpowers"):
        return "internal planning documentation"
    if relative.name in {"AGENTS.md", "review.md", "dev_log.md"}:
        return f"private repository file: {relative.name}"
    if relative.parent == Path(".") and re.fullmatch(r"task-\d+-report\.md", relative.name):
        return "internal task report at repository root"
    if relative.name == ".env":
        return "private environment file"
    if relative.suffix.lower() in {".crt", ".key", ".pem"} and not _is_dependency_license_fixture(relative):
        return "tracked TLS certificate or private-key file"
    return None


def _private_registry_host(line: str) -> str | None:
    """Return the registry host of a ``FROM`` line that pulls from a private registry.

    A leading path segment carrying a dot or a port is a registry rather than a
    Docker Hub namespace, so anything outside the public allowlist is a pull from
    somebody's internal infrastructure.
    """
    match = _DOCKERFILE_FROM.match(line)
    if match is None:
        return None
    host = match.group("host")
    if "." not in host and ":" not in host:
        return None
    if host.split(":")[0] in {"localhost", "127.0.0.1"}:
        return None
    return None if host in _PUBLIC_REGISTRIES else host


def _content_findings(relative: Path, content: str) -> list[Finding]:
    findings: list[Finding] = []
    # These two files define the marker patterns and exercise them against sample
    # hosts, so they match by construction. Only the marker and registry checks are
    # waived; key detection still applies, and the patterns name no real host.
    posix_path = relative.as_posix()
    defines_patterns = posix_path in _PATTERN_SOURCE_FILES
    # Vendored upstream bundles ship their own localizations; only our own
    # sources are held to the English-only rule.
    skips_language_check = defines_patterns or posix_path.startswith(_CYRILLIC_EXEMPT_PREFIXES)
    for line_number, line in enumerate(content.splitlines(), start=1):
        lowered = line.lower()
        if not defines_patterns:
            for label, pattern in PRIVATE_MARKER_PATTERNS:
                match = pattern.search(lowered)
                if match:
                    findings.append(
                        Finding(
                            relative.as_posix(),
                            f"private marker: {label} ({match.group(0)})",
                            line_number,
                        )
                    )
                    break
            registry = _private_registry_host(line)
            if registry is not None:
                findings.append(
                    Finding(relative.as_posix(), f"private registry base image: {registry}", line_number)
                )
        if _PRIVATE_KEY_HEADER.lower() in lowered:
            findings.append(Finding(relative.as_posix(), "PEM private-key header", line_number))

        if not skips_language_check and _CYRILLIC.search(line):
            findings.append(
                Finding(relative.as_posix(), "non-English (Cyrillic) source text", line_number)
            )

        key, separator, value = line.partition("=")
        if not separator or not key.strip().upper().endswith("_API_KEY"):
            continue
        value = value.split("#", 1)[0].strip().strip("'\"")
        if not value.lower().startswith("sk-") or len(value[3:]) < 20:
            continue
        if any(value.lower().startswith(f"sk-{placeholder}-") for placeholder in _SECRET_PLACEHOLDERS):
            continue
        findings.append(Finding(relative.as_posix(), "live-looking API key", line_number))
    return findings


def scan_tree(root: Path, *, tracked_only: bool | None = None) -> list[Finding]:
    """Return sorted release-hygiene findings for *root*."""
    root = root.resolve()
    use_tracked = tracked_only if tracked_only is not None else (root / ".git").exists()
    paths = _paths_from_git(root) if use_tracked else _paths_from_tree(root)
    findings: list[Finding] = []

    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        path_reason = _path_finding(relative)
        if path_reason:
            findings.append(Finding(relative.as_posix(), path_reason))
            continue

        try:
            raw_content = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw_content:
            continue
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        content_findings = _content_findings(relative, content)
        if relative.suffix.lower() in {".crt", ".key", ".pem"}:
            content_findings = [
                finding for finding in content_findings if finding.reason != "PEM private-key header"
            ]
        findings.extend(content_findings)

    return sorted(findings, key=lambda finding: (finding.path, finding.line or 0, finding.reason))


def check_required_files(root: Path) -> list[Finding]:
    """Return one finding for every mandatory public release file that is absent."""
    root = root.resolve()
    return [
        Finding(relative, "missing required public file")
        for relative in sorted(REQUIRED_PUBLIC_FILES)
        if not (root / relative).is_file()
    ]


def _normalized_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _numeric_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def check_streamlit_base_dependencies(root: Path) -> list[Finding]:
    root = root.resolve()
    requirements = root / _BASE_REQUIREMENTS
    dockerfile = root / _BASE_DOCKERFILE
    if not requirements.is_file():
        return []

    findings: list[Finding] = []
    versions: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        requirements.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXACT_REQUIREMENT.fullmatch(line)
        if match is None:
            findings.append(
                Finding(
                    _BASE_REQUIREMENTS,
                    f"dependency must use an exact == pin: {line}",
                    line_number,
                )
            )
            continue
        versions[_normalized_package_name(match.group("name"))] = match.group("version")

    for name, minimum in _SAFE_BASE_MINIMUMS.items():
        found = versions.get(name)
        if found is None:
            findings.append(Finding(_BASE_REQUIREMENTS, f"missing security dependency: {name}"))
        elif _numeric_version(found) < _numeric_version(minimum):
            findings.append(
                Finding(
                    _BASE_REQUIREMENTS,
                    f"{name} {found} is below the safe minimum {minimum}",
                )
            )

    if dockerfile.is_file():
        docker_text = dockerfile.read_text(encoding="utf-8")
        if "COPY requirements.txt /tmp/requirements.txt" not in docker_text:
            findings.append(
                Finding(_BASE_DOCKERFILE, "Dockerfile must copy streamlit-base/requirements.txt")
            )
        if "-r /tmp/requirements.txt" not in docker_text:
            findings.append(
                Finding(_BASE_DOCKERFILE, "Dockerfile must install streamlit-base/requirements.txt")
            )
    return findings


_SETTINGS_SOURCE = "backend/app/config.py"
_ENV_EXAMPLE = ".env.example"
_ENV_ASSIGNMENT = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=")


def _settings_field_names(source: Path) -> list[str]:
    """Return the annotated field names of the ``Settings`` class."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return [
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id.isupper()
            ]
    return []


def check_settings_documented(root: Path) -> list[Finding]:
    """Report settings that operators cannot discover from ``.env.example``.

    Every field is environment-configurable, so one absent from the sample file
    is invisible to anyone deploying the stack. A commented-out key counts as
    documented — that is how optional overrides are shown.
    """
    root = root.resolve()
    source = root / _SETTINGS_SOURCE
    env_example = root / _ENV_EXAMPLE
    if not source.is_file() or not env_example.is_file():
        return []

    documented = {
        match.group(1)
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if (match := _ENV_ASSIGNMENT.match(line))
    }
    return [
        Finding(_ENV_EXAMPLE, f"setting missing from the sample environment: {name}")
        for name in _settings_field_names(source)
        if name not in documented
    ]


_VERSION_SOURCES = {
    "backend/app/main.py": re.compile(r'^\s*version="(?P<version>[^"]+)"', re.MULTILINE),
    "frontend/package.json": re.compile(r'"version"\s*:\s*"(?P<version>[^"]+)"'),
    "e2e/package.json": re.compile(r'"version"\s*:\s*"(?P<version>[^"]+)"'),
    "CHANGELOG.md": re.compile(r"^##\s*\[(?P<version>\d+\.\d+\.\d+)\]", re.MULTILINE),
}


def check_versions_aligned(root: Path) -> list[Finding]:
    """Report component versions that disagree with the newest changelog entry.

    Bug reports ask for a version, so the number the API serves, the one the
    packages declare, and the one the changelog documents have to be the same.
    """
    root = root.resolve()
    versions: dict[str, str] = {}
    for relative, pattern in _VERSION_SOURCES.items():
        path = root / relative
        if not path.is_file():
            continue
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match:
            versions[relative] = match.group("version")

    expected = versions.get("CHANGELOG.md")
    if expected is None:
        return []
    return [
        Finding(relative, f"version {found} does not match the changelog's {expected}")
        for relative, found in sorted(versions.items())
        if relative != "CHANGELOG.md" and found != expected
    ]


def _local_link_target(raw_target: str) -> str | None:
    """Return a decoded local file target, or ``None`` for non-file links."""
    target = raw_target.strip()
    if not target or target.startswith("#"):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return unquote(parts.path)


def _normalize_reference_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def _reference_image_label(match: re.Match[str]) -> str:
    """Return the explicit or implicit CommonMark image-reference label."""
    reference = match.group("reference")
    return _normalize_reference_label(reference or match.group("alt"))


def check_markdown_links(root: Path) -> list[Finding]:
    """Validate local Markdown file links below *root*.

    Fragments and query strings identify content within a linked file, so the
    check verifies only the decoded path portion. Network and email URLs do
    not belong to the release tree and are deliberately ignored.
    """
    root = root.resolve()
    findings: list[Finding] = []
    for document in root.rglob("*.md"):
        relative_document = document.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative_document.parts):
            continue
        try:
            lines = document.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        reference_image_labels = {
            _reference_image_label(match)
            for line in lines
            for match in _REFERENCE_IMAGE.finditer(line)
        }
        for line_number, line in enumerate(lines, start=1):
            matches = list(_MARKDOWN_LINK.finditer(line))
            reference_definition = _MARKDOWN_REFERENCE_DEFINITION.match(line)
            if reference_definition is not None:
                matches.append(reference_definition)
            for match in matches:
                is_image = (
                    match.re is _MARKDOWN_LINK and bool(match.group("image"))
                ) or (
                    match.re is _MARKDOWN_REFERENCE_DEFINITION
                    and _normalize_reference_label(match.group("label"))
                    in reference_image_labels
                )
                raw_target = match.group("angle") or match.group("bare") or ""
                local_target = _local_link_target(raw_target)
                if local_target is None:
                    continue
                target = (document.parent / local_target).resolve()
                try:
                    target_relative = target.relative_to(root)
                except ValueError:
                    findings.append(
                        Finding(
                            relative_document.as_posix(),
                            f"Markdown link target outside release tree: {raw_target}",
                            line_number,
                        )
                    )
                    continue
                if (
                    is_image
                    and target_relative.as_posix() == _DEFERRED_SCREENSHOT
                ):
                    continue
                if not target.is_file():
                    findings.append(
                        Finding(
                            relative_document.as_posix(),
                            f"missing Markdown link target: {raw_target}",
                            line_number,
                        )
                    )
    return sorted(findings, key=lambda finding: (finding.path, finding.line or 0, finding.reason))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--all-files", action="store_true", help="scan all files, not only tracked files")
    args = parser.parse_args()

    findings = scan_tree(args.root, tracked_only=False if args.all_files else None)
    findings.extend(check_required_files(args.root))
    findings.extend(check_streamlit_base_dependencies(args.root))
    findings.extend(check_settings_documented(args.root))
    findings.extend(check_versions_aligned(args.root))
    findings.extend(check_markdown_links(args.root))
    findings.sort(key=lambda finding: (finding.path, finding.line or 0, finding.reason))
    for finding in findings:
        location = finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        print(f"{location}: {finding.reason}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
