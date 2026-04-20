# GitHub Actions workflows

## pytest.yml

Runs the full lint+type+test suite on three platforms:

- ubuntu-latest (apt-installed system deps for Qt and
  libsndfile)
- windows-latest (pip wheels carry all binaries)
- macos-latest (pip wheels carry all binaries)

Triggers: push + pull_request against master.
Timeout: 15 minutes per platform.

fail-fast is disabled so every OS runs to completion
even when one fails. CI is ready to flip to required
status checks (see "Required status check" below).

## Steps per platform

1. Checkout repo
2. Set up Python 3.12 with pip cache
3. (Linux only) Install Qt + libsndfile system deps
4. Upgrade pip
5. Install `requirements.txt` and `requirements-dev.txt`
6. `ruff check .`
7. `ruff format --check .`
8. `mypy src/lightconductor/`
9. `pytest tests/ -q --cov=src/lightconductor ...`
10. Upload HTML coverage report (artifact per OS)

## Linting

`ruff check` and `ruff format --check` run against the
entire repo before pytest.

Configuration lives in `pyproject.toml` under
`[tool.ruff]` — minimal selection: `E, F, I, B`. Line
length 88. Python target 3.12.

Per-file exceptions (see `pyproject.toml`):
- `tests/*` allows E402 for the `sys.path.insert`
  pattern used to locate the package without install.
- `main.py` allows E402 for the same reason (bootstrap).

No badges yet.

## Type checking

`mypy src/lightconductor/` runs before pytest.

Configuration lives in `pyproject.toml` under
`[tool.mypy]`. The entire `src/lightconductor/` tree
is under mypy strict mode:

- `lightconductor.domain.*`
- `lightconductor.application.*`
- `lightconductor.infrastructure.*`
- `lightconductor.presentation.*`

Third-party modules without stubs (librosa, pyqtgraph,
numpy, etc.) are marked `ignore_missing_imports`.

Each package has its own `[[tool.mypy.overrides]]`
block with the strict flags expanded explicitly, to
work around mypy#11401 (the leaking-globally bug of
`strict = true` inside overrides).

No badges.

## Coverage

`pytest tests/ -q --cov=src/lightconductor` runs as
part of the pytest step. HTML report is uploaded as
a GitHub Actions artifact, one per platform
(`coverage-html-ubuntu-latest`,
`coverage-html-windows-latest`,
`coverage-html-macos-latest`, 14-day retention).

Coverage gate: `--cov-fail-under=80` applied across all
three platforms. Baseline on Linux is 88.51% (measured
in 7.4a); the 80% threshold gives ~8% headroom to absorb
platform variance and minor regressions. A tightening to
85% is a future consideration once cross-platform numbers
stabilize over several weeks of CI data.

Coverage artifact (HTML) is uploaded per OS and browsable
in the run summary.

Coverage config lives in `pyproject.toml` under
`[tool.coverage.run]` / `[tool.coverage.report]`:
branch coverage enabled, `__init__.py` omitted, Protocol
method bodies excluded via `exclude_lines`.

## Required status check

After this PR merges and the pipeline proves stable on a
few master commits, repo owners should mark the pytest
workflow as a required status check so red CI blocks
merges.

Steps in GitHub UI:

1. Go to the repo's Settings → Branches.
2. Under "Branch protection rules", edit the rule for
   `master` (or create one if none exists).
3. Enable "Require status checks to pass before merging".
4. Search for and select these checks:
   - `pytest (ubuntu-latest)`
   - `pytest (windows-latest)`
   - `pytest (macos-latest)`
5. Enable "Require branches to be up to date before
   merging" (optional but recommended).
6. Save.

After this flip, PRs cannot merge until all three OS jobs
pass (which means ruff + mypy + pytest-with-80%-coverage
on each platform).
