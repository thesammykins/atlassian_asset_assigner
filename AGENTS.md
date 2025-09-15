# Repository Guidelines

## Project Structure & Module Organization
- `src/`: application code — `main.py` (CLI), `asset_manager.py`, `jira_assets_client.py`, `jira_user_client.py`, `config.py`.
- `tests/`: test scripts — `test_single_laptop.py`, `test_retirement.py`, `debug_hw615.py` (dry‑run friendly).
- `backups/` and `logs/`: created at runtime; safe to delete locally.
- Root files: `requirements.txt`, `dev-requirements.txt`, `.env.example` (copy to `.env`), `docs/`, `README.md`.

## Build, Test, and Development Commands
- Create env: `python3 -m venv venv && source venv/bin/activate`
- Install deps: `pip install -r requirements.txt`; dev: `pip install -r dev-requirements.txt`
- CLI help: `python src/main.py --help`
- Single asset (dry run): `python src/main.py --test-asset HW-0003`
- Bulk assign (dry run): `python src/main.py --bulk --dry-run`
- Retirement (dry run): `python src/main.py --retire-assets --dry-run`
- OAuth setup (one-time): `python src/main.py --oauth-setup`
- Tests (scripted): `python tests/test_single_laptop.py` and `python tests/test_retirement.py`
- Pytest (optional): `pytest -q tests` or focused `pytest -k retirement -q tests`

## Coding Style & Naming Conventions
- PEP 8 with 4-space indentation; include type hints and docstrings.
- Names: files/functions `snake_case` (e.g., `process_retirement`), classes `CamelCase`.
- Avoid side effects at import; keep API boundaries in `asset_manager` and `jira_*_client` modules.

## Formatting & Linting (Recommended)
- Black: `black src tests *.py`
- Ruff: `ruff check src tests` and auto-fix `ruff check --fix src tests`
- Type checks (optional): `mypy src`

## Testing Guidelines
- Prefer dry runs to avoid live mutations; test scripts print clear pass/fail.
- Place unit tests under `tests/` as `test_*.py`; mock external calls (e.g., `requests`).
- Isolate config in tests via a temp `.env` or monkeypatching.
- CI runs `pytest` only against `tests/` to avoid hitting live APIs.

## Commit & Pull Request Guidelines
- Conventional Commits (examples): `feat: ...`, `fix: ...`, `chore: ...`.
- Commits are small, descriptive, and scoped to one concern.
- PRs include purpose, linked issues, validation steps (commands/logs), and screenshots/snippets when helpful.
- Never commit secrets or `.env`; update `README.md`/`docs/` when CLI or config changes.

## Security & Configuration Tips
- Copy `.env.example` to `.env`; keep credentials local and out of VCS.
- OAuth tokens stored at `~/.jira_assets_oauth_token.json`; rotate regularly.
- Start with `--dry-run` before `--execute` in any environment.

