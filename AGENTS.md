# Repository Guidelines

This repository contains a PySide6-based Discord auto-reply desktop app plus scripts for licensing and Windows packaging. Use the instructions below to keep contributions consistent and safe.

## Project Structure & Module Organization
- `src/` holds the app modules: `main.py` (entry), `gui.py` (UI), `discord_client.py` (Discord logic), and `config_manager.py` (config I/O).
- `config/` contains runtime configuration (see `example_config.json` for a template).
- `assets/` stores images/icons used by the GUI.
- Root scripts (`run.py`, `build_exe.py`, `create_license.py`, `manage_license.py`, `batch_create_licenses.py`) are developer utilities.
- `.github/workflows/` defines CI for Windows EXE builds.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` - install Python deps (Python 3.8+).
- `python run.py` - start the GUI with local config.
- `python build_exe.py` - build the Windows EXE via Nuitka (run on Windows).
- `python create_license.py <server> <user> <pass> [license_id]` - create a license.
- `python manage_license.py <action> <server> <user> <pass> <license_id>` - validate/activate/update licenses.

## Coding Style & Naming Conventions
- Use 4-space indentation and keep code close to existing PEP 8 style.
- Modules and functions use `snake_case`; classes use `CamelCase`; constants use `UPPER_SNAKE_CASE`.
- Prefer relative imports inside `src/` (e.g., `from .discord_client import ...`).

## Testing Guidelines
- There is no automated test suite in this repo.
- For validation, run `python run.py` and exercise the GUI flows you touched.
- If you add tests, place them in `tests/` with `test_*.py` names and document the runner you choose.

## Commit & Pull Request Guidelines
- Recent commits use `feat:`, `fix:`, and `docs:` prefixes, along with a few generic `update` messages. Prefer the prefixed style with a short, imperative summary.
- PRs should include: what changed, why, how to verify, and screenshots for UI changes. Link related issues when available.

## Security & Configuration Tips
- `config/config.json` can contain real Discord tokens and license credentials; do not commit sensitive values. Use `config/example_config.json` for shareable defaults.
- Avoid hardcoding secrets in source; pass them via local config or environment variables.
