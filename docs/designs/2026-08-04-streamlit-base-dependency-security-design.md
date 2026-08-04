# Streamlit Base Dependency Security Design

## Goal

Make the Streamlit application runtime reproducible and keep known vulnerable
Python packages out of OSS releases. The change covers the vulnerable packages
found during the 0.1.0 release audit and adds an automated dependency-security
gate for both backend and Streamlit-base dependencies.

## Scope

- Move every Python package installed by `streamlit-base/Dockerfile` into
  `streamlit-base/requirements.txt`.
- Pin every direct dependency with `==`; hashes are intentionally out of scope.
- Upgrade the vulnerable direct packages to these minimum fixed versions:
  `streamlit==1.54.0`, `requests==2.33.0`, `pyarrow==23.0.1`,
  `python-dotenv==1.2.2`, and `pillow==12.3.0`.
- Preserve the remaining direct package versions unless dependency resolution or
  application compatibility requires a targeted change.
- Add weekly Dependabot coverage for `/streamlit-base` using the `pip`
  ecosystem.
- Run `pip-audit==2.10.1` in CI against both `backend/requirements.txt` and
  `streamlit-base/requirements.txt`.
- Document the new local release-security command.

Publishing prebuilt images, adding hashes, SBOM generation, image signing, and
upgrading unrelated backend or frontend dependencies are out of scope.

## File responsibilities

- `streamlit-base/requirements.txt`: single source of truth for direct packages
  installed into user-application images.
- `streamlit-base/Dockerfile`: image user, filesystem and runtime configuration;
  it copies and installs the requirements file in one layer.
- `.github/dependabot.yml`: weekly update discovery for the new pip dependency
  directory.
- `.github/workflows/ci.yml`: blocking advisory scan for backend and base-image
  Python dependencies.
- `scripts/check_release.py`: release invariants requiring the dependency file,
  exact direct pins, Dockerfile indirection, and fixed-version floors for the
  five audited packages.
- `scripts/tests/test_check_release.py`: regression coverage for every new
  release invariant.
- `docs/development.md` and `CONTRIBUTING.md`: contributor commands and release
  evidence requirements.
- `CHANGELOG.md`: unreleased security and supply-chain changes.

## Dependency flow

Dependabot reads `streamlit-base/requirements.txt` and proposes updates. CI
first validates that direct dependencies remain exactly pinned, then resolves
the backend and base requirements independently with `pip-audit`. The Docker
build installs exactly the same base requirements file, so the audited direct
dependency set and the built image cannot drift through duplicated Dockerfile
package lists.

Transitive dependencies remain resolver-selected because this design does not
introduce hashes or a generated transitive lock. A clean Docker build and E2E
suite are therefore required after direct dependency changes.

## Failure behavior

- Release hygiene fails when the base requirements file is absent, a direct
  dependency is not exactly pinned, the Dockerfile stops installing that file,
  or one of the five security-sensitive packages falls below its fixed floor.
- CI fails when `pip-audit` reports any known advisory for either dependency
  set.
- Docker build or E2E failures block the dependency update; versions are not
  relaxed to bypass compatibility errors.

## Verification

1. Run the new release-checker tests red before implementation and green after
   implementation.
2. Resolve and audit both Python requirement sets.
3. Run the complete release-hygiene, backend lint and backend test suites.
4. Build `streamlit-base` without cache and inspect the installed versions.
5. Build the full Compose stack and run the E2E suite when host ports are
   available; otherwise the GitHub Actions E2E job is the required release
   gate.
6. Confirm the exported Git tree passes `scripts/check_release.py --all-files`.

## Success criteria

- `pip-audit` reports no known vulnerabilities for backend or Streamlit-base
  requirements.
- The five vulnerable packages resolve at or above the versions listed in this
  design.
- Dependabot recognizes `/streamlit-base` as a pip directory.
- Release checks, tests and clean Docker builds pass without changing the
  documented runtime isolation properties.
