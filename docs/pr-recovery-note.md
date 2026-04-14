# PR recovery note

This commit recreates the lost PR context for the startup import fix.

## Restored change set
- switched fragile package-level imports to direct module imports in:
  - `MainScreen/MainScreen.py`
  - `ProjectScreen/ProjectScreen.py`
  - `src/lightconductor/presentation/project_controller.py`

## Why this was needed
Some local environments raised:
`ImportError: cannot import name 'LegacyMastersMapper' from 'lightconductor.infrastructure'`.
Direct submodule imports avoid dependence on package re-export state and stale caches.
