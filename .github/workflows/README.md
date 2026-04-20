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
even when one fails. CI stays informational (no
required status check) until roadmap 7.4c.

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

No threshold is currently enforced — this is a baseline
measurement phase (roadmap 7.4a). Baseline 88.51% was
measured on Linux in 7.4a; cross-platform numbers become
visible after 7.4b's first green runs. A fail-under gate
(target ≥70%) lands in roadmap 7.4c after cross-platform
stabilization.

Coverage config lives in `pyproject.toml` under
`[tool.coverage.run]` / `[tool.coverage.report]`:
branch coverage enabled, `__init__.py` omitted, Protocol
method bodies excluded via `exclude_lines`.
