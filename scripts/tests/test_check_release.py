from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
from unittest import TestCase

from scripts import check_release
from scripts.check_release import (
    check_markdown_links,
    check_required_files,
    check_settings_documented,
    check_versions_aligned,
    scan_tree,
)


class ReleaseHygieneTests(TestCase):
    def scan(self, files: dict[str, str]):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, content in files.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return scan_tree(root)

    def test_accepts_safe_release_files(self):
        self.assertEqual(
            self.scan(
                {
                    "README.md": "# STHub\n",
                    ".env.example": "AI_API_KEY=\n",
                    "tests/test_auth.py": 'token = "test-token"\n',
                    "docs/ai.md": "AI_API_KEY=sk-short # explanatory prose that is deliberately long\n",
                    "Dockerfile": "FROM python:3.12-slim\n",
                    "compose.yaml": "    image: quay.io/keycloak/keycloak:25.0\n",
                    "certs/generate-certs.sh": "#   CERT_HOST=sthub.local ./certs/generate-certs.sh\n",
                }
            ),
            [],
        )

    def test_gitleaks_monaco_allowlist_matches_container_paths(self):
        """The vendored Monaco exception must work with Gitleaks' /repo paths."""
        config = tomllib.loads((Path(__file__).parents[2] / ".gitleaks.toml").read_text())
        pattern = config["allowlists"][0]["paths"][0]

        self.assertRegex("frontend/public/monaco-editor/min/vs/editor/editor.main.js", pattern)
        self.assertRegex("/repo/frontend/public/monaco-editor/min/vs/editor/editor.main.js", pattern)
        self.assertNotRegex("/tmp/frontend/public/monaco-editor/min/vs/editor/editor.main.js", pattern)
        self.assertNotRegex("malicious/frontend/public/monaco-editor/min/vs/editor/editor.main.js", pattern)
        self.assertNotRegex("/repo/frontend/public/monaco-editor/LICENSE", pattern)

    def test_rejects_private_infrastructure_markers(self):
        findings = self.scan(
            {
                "config.txt": "https://apps.example-zone.local\n",
                "frontend.env": "https://sso-dev.idp.example-company.corp\n",
                "printer.txt": "smb://files.example-office.lan/share\n",
            }
        )
        self.assertEqual(len(findings), 3)

    def test_rejects_non_english_source_text(self):
        """The UI and API messages are English; Cyrillic means a regression."""
        findings = self.scan({"frontend/src/app/page.tsx": "const label = 'Привет';\n"})

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "non-English (Cyrillic) source text")

    def test_allows_cyrillic_in_vendored_monaco_bundle(self):
        """Upstream Monaco ships its own localizations and is not ours to police."""
        self.assertEqual(
            self.scan(
                {"frontend/public/monaco-editor/min/vs/editor/editor.main.nls.ru.js": "'Привет'\n"}
            ),
            [],
        )

    def test_rejects_private_registry_base_image(self):
        """A Dockerfile pulling from a non-public registry is a release-hygiene finding."""
        findings = self.scan({"Dockerfile": "FROM registry.example-company.net/python:3.12\n"})

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].reason,
            "private registry base image: registry.example-company.net",
        )

    def test_allows_public_registry_and_bare_base_images(self):
        """Docker Hub shorthand and allowlisted public registries must pass."""
        self.assertEqual(
            self.scan(
                {
                    "a/Dockerfile": "FROM python:3.12-slim\n",
                    "b/Dockerfile": "FROM ghcr.io/owner/image:1.0\n",
                    "c/Dockerfile": "FROM library/postgres:16-alpine\n",
                }
            ),
            [],
        )

    def test_allows_single_label_local_development_hostname(self):
        """A one-label .local name is a dev convention, not an internal AD zone."""
        self.assertEqual(
            self.scan({"certs/generate-certs.sh": "CERT_HOST=sthub.local\n"}),
            [],
        )

    def test_rejects_private_certificate_directory_marker(self):
        """A private certificate path must remain a release-hygiene finding."""
        findings = self.scan(
            {
                "compose.yml": "certificate = /opt/pki/example/service-ca.pem\n",
            }
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "private marker: internal PKI path (/opt/pki/)")

    def test_rejects_generated_and_private_paths(self):
        findings = self.scan(
            {
                "backend/.review-venv/bin/python": "",
                "frontend/.next/server.js": "",
                "design/export.zip": "",
                ".env": "SECRET=value\n",
                "docs/superpowers/plans/internal.md": "",
                "docs/plans/2026-01-01-feature.md": "",
            }
        )
        self.assertEqual(len(findings), 6)
        self.assertEqual(
            {finding.reason for finding in findings if finding.path.startswith("docs/")},
            {"internal planning documentation"},
        )

    def test_allows_published_design_rationale(self):
        self.assertEqual(self.scan({"docs/designs/dependency-security.md": "# Goal\n"}), [])

    def test_rejects_root_internal_task_report(self):
        findings = self.scan({"task-8-report.md": "internal\n"})
        self.assertEqual(findings[0].reason, "internal task report at repository root")

    def test_allows_nested_public_task_report(self):
        self.assertEqual(self.scan({"docs/task-8-report.md": "public\n"}), [])

    def test_rejects_ignored_virtualenv_and_auth_paths(self):
        findings = self.scan(
            {
                "venv/bin/python": "",
                ".auth/state.json": "{}",
            }
        )
        self.assertEqual(len(findings), 2)

    def test_rejects_private_keys_and_live_looking_api_keys(self):
        findings = self.scan(
            {
                "key.pem": "-----BEGIN " "PRIVATE KEY-----\nabc\n",
                "settings.txt": "AI_API_KEY" "=" "sk-live-looking-value-1234567890\n",
            }
        )
        self.assertEqual(len(findings), 2)

    def test_rejects_live_key_containing_a_fake_substring(self):
        findings = self.scan(
            {
                "settings.txt": "AI_API_KEY"
                "="
                "sk-live-looking-test-substring-1234567890\n"
            }
        )
        self.assertEqual(len(findings), 1)

    def test_reports_each_missing_public_file(self):
        """Removing a required release document must make the checker fail."""
        with TemporaryDirectory() as tmp:
            findings = check_required_files(Path(tmp))

        missing = {finding.path for finding in findings}
        self.assertIn("README.md", missing)
        self.assertIn("LICENSE", missing)
        self.assertIn("THIRD_PARTY_NOTICES.md", missing)
        self.assertIn("docs/api-contract.md", missing)
        self.assertIn(".github/dependabot.yml", missing)
        self.assertIn("frontend/public/monaco-editor/ThirdPartyNotices.txt", missing)
        self.assertIn("streamlit-base/requirements.txt", missing)

    def test_reports_missing_streamlit_base_dependency_automation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "dependabot.yml").write_text(
                "version: 2\nupdates: []\n", encoding="utf-8"
            )
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "name: CI\n", encoding="utf-8"
            )

            findings = check_release.check_dependency_security_automation(root)

        reasons = {finding.reason for finding in findings}
        self.assertIn("Dependabot must scan /streamlit-base as pip", reasons)
        self.assertIn("CI must install a pinned pip-audit==<version>", reasons)
        self.assertIn("CI must audit backend/requirements.txt", reasons)
        self.assertIn("CI must audit streamlit-base/requirements.txt", reasons)

    def _automation_root(self, tmp: str, auditor: str) -> Path:
        root = Path(tmp)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "dependabot.yml").write_text(
            "package-ecosystem: pip\ndirectory: /streamlit-base\n",
            encoding="utf-8",
        )
        (root / ".github" / "workflows" / "ci.yml").write_text(
            f"python -m pip install {auditor}\n"
            "pip-audit -r backend/requirements.txt\n"
            "pip-audit -r streamlit-base/requirements.txt\n",
            encoding="utf-8",
        )
        return root

    def test_accepts_complete_streamlit_base_dependency_automation(self):
        with TemporaryDirectory() as tmp:
            root = self._automation_root(tmp, "pip-audit==2.10.1")

            self.assertEqual(check_release.check_dependency_security_automation(root), [])

    def test_accepts_a_pip_audit_upgrade(self):
        """Pinning a specific auditor version here would block its own upgrade."""
        with TemporaryDirectory() as tmp:
            root = self._automation_root(tmp, "pip-audit==2.11.0")

            self.assertEqual(check_release.check_dependency_security_automation(root), [])

    def test_rejects_an_unpinned_pip_audit(self):
        with TemporaryDirectory() as tmp:
            root = self._automation_root(tmp, "pip-audit")

            findings = check_release.check_dependency_security_automation(root)

        reasons = {finding.reason for finding in findings}
        self.assertIn("CI must install a pinned pip-audit==<version>", reasons)

    def test_rejects_unpinned_and_vulnerable_streamlit_base_dependencies(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "streamlit-base").mkdir()
            (root / "streamlit-base" / "requirements.txt").write_text(
                "streamlit==1.39.0\nrequests>=2.33.0\nnumpy==1.26.*\n",
                encoding="utf-8",
            )
            (root / "streamlit-base" / "Dockerfile").write_text(
                "FROM python:3.12-slim\nRUN pip install streamlit\n",
                encoding="utf-8",
            )

            findings = check_release.check_streamlit_base_dependencies(root)

        reasons = {finding.reason for finding in findings}
        self.assertIn("dependency must use an exact == pin: requests>=2.33.0", reasons)
        self.assertIn("dependency must use an exact == pin: numpy==1.26.*", reasons)
        self.assertIn("streamlit 1.39.0 is below the safe minimum 1.54.0", reasons)
        self.assertIn("Dockerfile must copy streamlit-base/requirements.txt", reasons)
        self.assertIn("Dockerfile must install streamlit-base/requirements.txt", reasons)

    def test_accepts_exact_safe_streamlit_base_dependencies(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "streamlit-base").mkdir()
            (root / "streamlit-base" / "requirements.txt").write_text(
                "\n".join(
                    [
                        "streamlit==1.54.0",
                        "requests==2.33.0",
                        "pyarrow==23.0.1",
                        "python-dotenv==1.2.2",
                        "pillow==12.3.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "streamlit-base" / "Dockerfile").write_text(
                "COPY requirements.txt /tmp/requirements.txt\n"
                "RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt\n",
                encoding="utf-8",
            )

            self.assertEqual(check_release.check_streamlit_base_dependencies(root), [])

    def _base_dependencies(self, tmp: str, requirements: str) -> list:
        root = Path(tmp)
        (root / "streamlit-base").mkdir()
        (root / "streamlit-base" / "requirements.txt").write_text(
            requirements, encoding="utf-8"
        )
        (root / "streamlit-base" / "Dockerfile").write_text(
            "COPY requirements.txt /tmp/requirements.txt\n"
            "RUN pip install -r /tmp/requirements.txt\n",
            encoding="utf-8",
        )
        return check_release.check_streamlit_base_dependencies(root)

    def test_accepts_pins_carrying_suffixes_markers_and_comments(self):
        """These are all exact pins; only the operator decides, not the notation."""
        with TemporaryDirectory() as tmp:
            findings = self._base_dependencies(
                tmp,
                "streamlit==1.54.0  # audited for CVE coverage\n"
                "requests==2.33.0 ; python_version >= '3.9'\n"
                "pyarrow==23.0.1\n"
                "python-dotenv==1.2.2\n"
                "pillow==12.3.0.post1\n",
            )

        self.assertEqual(findings, [])

    def test_rejects_a_pre_release_of_the_fixed_version(self):
        """23.0.1rc1 predates the fix that shipped in 23.0.1."""
        with TemporaryDirectory() as tmp:
            findings = self._base_dependencies(
                tmp,
                "streamlit==1.54.0\nrequests==2.33.0\npyarrow==23.0.1rc1\n"
                "python-dotenv==1.2.2\npillow==12.3.0\n",
            )

        reasons = {finding.reason for finding in findings}
        self.assertIn("pyarrow 23.0.1rc1 is below the safe minimum 23.0.1", reasons)

    def test_accepts_a_shorter_release_that_meets_the_floor(self):
        with TemporaryDirectory() as tmp:
            findings = self._base_dependencies(
                tmp,
                "streamlit==1.54\nrequests==2.33.0\npyarrow==23.0.1\n"
                "python-dotenv==1.2.2\npillow==12.3.0\n",
            )

        self.assertEqual(findings, [])

    def test_reports_settings_absent_from_the_sample_environment(self):
        """An operator can only discover a setting if .env.example names it."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend" / "app").mkdir(parents=True)
            (root / "backend" / "app" / "config.py").write_text(
                "class Settings(BaseSettings):\n"
                "    DATABASE_URL: str = 'postgresql://'\n"
                "    REDIS_URL: str = 'redis://'\n"
                "    AI_SYSTEM_PROMPT: str = 'hello'\n"
                "    UNDOCUMENTED_SETTING: int = 1\n",
                encoding="utf-8",
            )
            (root / ".env.example").write_text(
                "DATABASE_URL=postgresql://\nREDIS_URL=redis://\n# AI_SYSTEM_PROMPT=\n",
                encoding="utf-8",
            )

            findings = check_settings_documented(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, ".env.example")
        self.assertEqual(
            findings[0].reason,
            "setting missing from the sample environment: UNDOCUMENTED_SETTING",
        )

    def _version_tree(self, root: Path, backend: str, frontend: str, changelog: str) -> None:
        (root / "backend" / "app").mkdir(parents=True)
        (root / "backend" / "app" / "main.py").write_text(
            f'app = FastAPI(\n    title="STHub",\n    version="{backend}",\n)\n',
            encoding="utf-8",
        )
        (root / "frontend").mkdir()
        (root / "frontend" / "package.json").write_text(
            f'{{\n  "name": "sthub-frontend",\n  "version": "{frontend}"\n}}\n',
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [Unreleased]\n\n## [{changelog}] - 2026-08-04\n",
            encoding="utf-8",
        )

    def test_reports_versions_that_disagree_with_the_changelog(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._version_tree(root, backend="0.1.0", frontend="0.2.0", changelog="0.1.0")

            findings = check_versions_aligned(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "frontend/package.json")
        self.assertEqual(
            findings[0].reason, "version 0.2.0 does not match the changelog's 0.1.0"
        )

    def test_accepts_versions_matching_the_changelog(self):
        """The Unreleased heading must not be mistaken for the released version."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._version_tree(root, backend="0.1.0", frontend="0.1.0", changelog="0.1.0")

            self.assertEqual(check_versions_aligned(root), [])

    def test_validates_missing_local_markdown_targets(self):
        """A broken local target must be reported while non-file URLs are ignored."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "\n".join(
                    [
                        "[valid](architecture.md#components)",
                        "[query](architecture.md?view=full#components)",
                        "[encoded](encoded%20name.md#section)",
                        "[external](https://example.com/docs)",
                        "[email](mailto:maintainer@example.com)",
                        "[fragment](#local-section)",
                        "![deferred](assets/dashboard.png)",
                        "[missing](missing.md)",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "docs" / "architecture.md").write_text("# Components\n", encoding="utf-8")
            (root / "docs" / "encoded name.md").write_text("# Section\n", encoding="utf-8")

            findings = check_markdown_links(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "docs/guide.md")
        self.assertEqual(findings[0].line, 8)
        self.assertEqual(findings[0].reason, "missing Markdown link target: missing.md")

    def test_ignores_markdown_in_excluded_dependency_directories(self):
        """Dependency documentation must not turn into release-link findings."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            dependency_readme = root / "frontend" / "node_modules" / "pkg" / "README.md"
            dependency_readme.parent.mkdir(parents=True)
            dependency_readme.write_text("[missing](nope.md)\n", encoding="utf-8")

            self.assertEqual(check_markdown_links(root), [])

    def test_validates_reference_style_markdown_links(self):
        """Reference definitions must resolve decoded local targets like inline links."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "[architecture][arch]\n[arch]: encoded%20architecture.md?view=full#components\n"
                "[missing][missing-ref]\n[missing-ref]: missing.md\n",
                encoding="utf-8",
            )
            (root / "docs" / "encoded architecture.md").write_text("# Components\n", encoding="utf-8")

            findings = check_markdown_links(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 4)
        self.assertEqual(findings[0].reason, "missing Markdown link target: missing.md")

    def test_ignores_deferred_reference_style_dashboard_image(self):
        """The deferred dashboard image is ignored through a reference definition."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![dashboard][shot]\n[shot]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            self.assertEqual(check_markdown_links(root), [])

    def test_ignores_deferred_collapsed_reference_dashboard_image(self):
        """A collapsed image reference inherits the alt text as its label."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![dashboard][]\n[dashboard]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            self.assertEqual(check_markdown_links(root), [])

    def test_ignores_deferred_shortcut_reference_dashboard_image(self):
        """A shortcut image reference inherits its alt text as its label."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![dashboard]\n[dashboard]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            self.assertEqual(check_markdown_links(root), [])

    def test_normalizes_collapsed_image_reference_label(self):
        """A collapsed image label is normalized independently."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![DASHBOARD   PREVIEW][]\n[ dashboard preview ]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            self.assertEqual(check_markdown_links(root), [])

    def test_normalizes_shortcut_image_reference_label(self):
        """A shortcut image label is normalized independently."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![DASHBOARD\tPREVIEW]\n[ dashboard preview ]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            self.assertEqual(check_markdown_links(root), [])

    def test_reports_non_deferred_collapsed_and_shortcut_image_references(self):
        """Only the dashboard target is deferred; other image references stay checked."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "![missing image][]\n"
                "![other image]\n"
                "[missing image]: assets/missing.png\n"
                "[other image]: assets/other.png\n",
                encoding="utf-8",
            )

            findings = check_markdown_links(root)

        self.assertEqual(len(findings), 2)
        self.assertEqual(
            [finding.reason for finding in findings],
            [
                "missing Markdown link target: assets/missing.png",
                "missing Markdown link target: assets/other.png",
            ],
        )

    def test_reports_dashboard_target_for_non_image_reference(self):
        """The deferred screenshot exception applies only to image references."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "[dashboard]\n[dashboard]: assets/dashboard.png\n",
                encoding="utf-8",
            )

            findings = check_markdown_links(root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "missing Markdown link target: assets/dashboard.png")
