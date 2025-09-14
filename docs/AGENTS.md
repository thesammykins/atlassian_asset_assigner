# Repository Guidelines

## Project Structure & Module Organization
- `src/`: application code — `main.py` (CLI), `asset_manager.py`, `jira_assets_client.py`, `jira_user_client.py`, `config.py`.
- Root test scripts: `test_single_laptop.py`, `test_retirement.py` (dry-run friendly).
- `backups/` and `logs/`: created at runtime; safe to delete locally.
- `requirements.txt`, `.env.example`, `.env` (not committed), `docs/`, `README.md`.

## Build, Test, and Development Commands
- Create env: `python3 -m venv venv && source venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Install dev deps: `pip install -r dev-requirements.txt`
- CLI help: `python src/main.py --help`
- Single asset (dry run): `python src/main.py --test-asset HW-459`
- Bulk assign (dry run): `python src/main.py --bulk --dry-run`
- Retirement (dry run): `python src/main.py --retire-assets --dry-run`
- OAuth setup (one-time): `python src/main.py --oauth-setup`
- Tests (scripted): `python test_single_laptop.py` and `python test_retirement.py`

## Coding Style & Naming Conventions
- Follow PEP 8, 4-space indentation; use type hints and docstrings.
- Files/functions: `snake_case` (e.g., `asset_manager.py`, `process_retirement`); classes: `CamelCase`.
- Avoid side effects at import; keep API boundaries in `asset_manager` and `jira_*_client` modules.
- No preconfigured linter/formatter; keep style consistent with existing code.

## Testing Guidelines
- Prefer dry runs to avoid live mutations; the provided scripts print clear pass/fail output.
- Pytest (optional): add `pytest` to dev deps and place tests in `tests/` as `test_*.py`.
  - Example: `pytest -q tests` or a focused run `pytest -k retirement -q tests`.
- Mock external calls (e.g., `requests`) to make tests deterministic; isolate config via temporary `.env` or monkeypatching.
- Quick checks: `python test_retirement.py` and `python test_single_laptop.py`.

CI runs `pytest` only against `tests/` to avoid hitting live APIs. Put unit tests there; keep e2e/manual scripts at repo root.

## Formatting & Linting (Recommended)
- Formatter: Black — `black src tests *.py` (configured in `pyproject.toml`).
- Linter: Ruff — `ruff check src tests` and auto-fix: `ruff check --fix src tests`.
- Type checks: optional `mypy` on `src/` once annotations are complete.

## Commit & Pull Request Guidelines
- Use Conventional Commits (examples from history): `feat: ...`, `chore: ...`, `fix: ...`.
- Commits: small, descriptive, scoped to one concern.
- PRs: include purpose, linked issues, how to validate (commands/logs), and screenshots/snippets when useful.
- Never include secrets or `.env`; update `README.md`/`docs/` when CLI or config changes.

## Security & Configuration Tips
- Copy `.env.example` to `.env`; do not commit `.env` or CSVs (already ignored).
- Tokens for OAuth are stored locally at `~/.jira_assets_oauth_token.json`; rotate regularly.
- Start with `--dry-run` before `--execute` in any environment.
