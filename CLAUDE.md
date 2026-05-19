# Codex Windows Usage Tool

## Project Goal

Build a local Windows desktop tool that parses Codex usage logs, stores request-level usage records locally, calculates token/cost summaries, and displays the data in a modern embedded React UI.

## Directory Structure

- `src/codex_usage_tool/`: application source code.
- `src/codex_usage_tool/core/`: log parsing, cost calculation, statistics, and persistence.
- `src/codex_usage_tool/ui/`: legacy PySide6 windows, widgets, themes, and chart views.
- `frontend/`: React Web UI served by the local Python API.
- `tests/`: unit tests for parser, statistics, and storage behavior.
- `docs/`: project notes and user-facing implementation documentation.
- `assets/`: application-owned static assets such as app icons. Store source PNGs and derived `.ico` files here.
- `scripts/`: local build and packaging scripts. Scripts must be repeatable and must not require global dependencies.
- `data/`: local generated SQLite/CSV outputs. Do not commit user usage data.

## Naming Rules

- Python modules use `snake_case.py`.
- Public dataclasses and widgets use `PascalCase`.
- Functions and variables use `snake_case`.
- Test files are named `test_<module>.py`.

## Sensitive Data Rules

- Do not read or modify `.env`, tokens, secrets, or CI/CD configuration.
- Do not parse `C:\Users\<user>\.codex\auth.json` in the first implementation.
- Do not commit local usage exports, SQLite databases, or raw Codex logs.
- Keep all collected data local unless the user explicitly requests an export.

## Runtime Rules

- Default log source: `%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl`.
- Fallback sources: `%USERPROFILE%\.codex\logs_2.sqlite` and `%USERPROFILE%\.codex\logs\*.jsonl`.
- Default SQLite path: source runs use `data/codex_usage.sqlite3`; packaged runs use `%LOCALAPPDATA%\CodexUsageTool\codex_usage.sqlite3`.
- The application must tolerate missing logs and malformed JSONL rows.
- Unknown models use a zero-cost fallback until pricing is configured in the React UI.

## Verification

Run these before reporting completion:

```powershell
python -m unittest discover -s tests
python -m compileall src tests
```

For GUI verification, run:

```powershell
python -m codex_usage_tool
```

For frontend verification:

```powershell
npm --prefix frontend run build
```

Install local project dependencies when needed:

```powershell
python -m pip install -r requirements.txt
```
