# GitHub Actions workflows

## pytest.yml

Runs `pytest tests/ -q` on ubuntu-latest with Python 3.12
on every push and every pull request against `master`.

### Scope

- pytest only. No ruff, no mypy, no coverage gate.
- Linux only. Cross-platform matrix is roadmap Phase 7.4.
- Informational: CI failures do not block merges. Making
  this a required status check is a follow-up.

### System dependencies

- libsndfile1: soundfile backend for librosa.
- libxkbcommon0, libegl1, libxcb-*: Qt/PyQt6 runtime on
  Ubuntu.
- libdbus-1-3, libfontconfig1, libxrender1: general X11
  stack Qt pulls in indirectly.

Qt runs headless via QT_QPA_PLATFORM=offscreen.

### Related roadmap items

- 7.2: ruff format + check (follow-up PR).
- 7.3: mypy --strict on src/lightconductor (follow-up PR).
- 7.4: coverage gate ≥ 70%; Linux/Windows/macOS matrix
  (follow-up PR).

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
`[tool.mypy]`. Strategy is gradual strictness:

- Baseline (conservative checks) across
  `src/lightconductor/`.
- Strict mode on `lightconductor.domain.*` and
  `lightconductor.application.*` (roadmap 7.3a).
- `lightconductor.infrastructure.*` moves to strict
  in roadmap 7.3b (follow-up).
- `lightconductor.presentation.*` moves to strict in
  roadmap 7.3c (follow-up).

Third-party modules without stubs (librosa, pyqtgraph,
numpy, etc.) are marked `ignore_missing_imports`.

No badges yet.
