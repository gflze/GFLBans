# Repository Guidelines

## Project Structure & Module Organization

GFLBans is a Python ASGI web application. Core application code lives in `gflbans/`: API routes are in `gflbans/api/`, web page handlers are in `gflbans/web/`, and database models, integrations, background tasks, configuration, and shared utilities are in `gflbans/internal/`. Static assets are stored in `static/`, with first-party CSS and JavaScript under `static/css/` and `static/js/`; vendored browser assets stay in `static/3rdparty/`. HTML templates are in `templates/`, including optional deploy-time examples in `templates/configs/*.example`. Utility scripts and import data live in `tools/`.

## Build, Test, and Development Commands

- `python -m venv venv`: create the local virtual environment.
- `venv\Scripts\activate` on Windows or `source venv/bin/activate` on Unix: activate the environment.
- `pip install -r requirements.txt`: install runtime and developer dependencies.
- `python -m gflbans.main`: run the application locally, using `.env` configuration, on the port documented in `README.md`.
- `pre-commit run --all-files`: run formatting and lint checks across Python, templates, JavaScript, and generic file hygiene.

Copy `.env.sample` to `.env` before running locally. Redis and MongoDB are required services.

## Coding Style & Naming Conventions

Python targets 3.13 and is formatted by Ruff with 4-space indentation, single quotes, import sorting, and a 120-character line limit. Use `snake_case` for modules, functions, and variables; keep route modules grouped by resource, such as `gflbans/api/infraction.py`.

JavaScript in `static/js/` uses ESLint with 4-space indentation, single quotes, semicolons, 1TBS brace style, and a 120-character line limit. Template formatting is handled by djLint; do not reformat or modify vendored files under `static/3rdparty/`.

## Testing Guidelines

No automated test suite is currently present in this repository. For changes, run `pre-commit run --all-files` and perform targeted manual verification by starting `python -m gflbans.main` against a configured local `.env`. If adding tests, place Python tests under a new `tests/` directory and name files `test_<feature>.py`.

## Commit & Pull Request Guidelines

Recent history uses concise, imperative commit subjects, with dependency updates following `Bump <package> from <old> to <new> (#<PR>)`. Keep commits focused and describe user-visible behavior or maintenance scope.

Pull requests should include a short summary. Note any required `.env` keys, database assumptions, or Redis/MongoDB setup changes.

## Security & Configuration Tips

Never commit `.env`, secrets, production credentials, API keys, or generated local data. Keep deploy-specific template overrides derived from `templates/configs/*.example` out of generic code changes unless the defaults themselves are changing.
