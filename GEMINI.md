# Project Guidelines: Pokemon Web App

## 1. Project Location & Workspace
- The project is located under `ag_coding`: `/Users/francistallo/Desktop/ag_coding/Pokemon/pokemon-web-app`

## 2. Python Environment & Execution
- Always execute Python scripts, tools, and tests directly using this project's dedicated virtual environment:
  - Python: `./.venv/bin/python`
  - Automated Unit Tests: `./.venv/bin/python -m unittest discover -s tests`
- Never execute naked `python` or `pytest` from the system PATH.
- Stick to dependencies declared in `pyproject.toml`, `requirements.txt`, or installed in `.venv`.

## 3. Architecture & Reviewer Conventions
- **Cache Management (`utils/cache.py`)**: All disk writes must use `_atomic_write` and thread locks (`RLock`/`Lock`) to prevent corruption.
- **Battle Engine (`utils/battle_engine.py`)**: Must strictly adhere to Generation 9 competitive tournament rules (damage formula, Protect decay, Struggle fallback, recoil capping).
- **Naming & Types (`utils/naming.py`, `utils/type_effectiveness.py`)**: Use LRU memoization (`@functools.lru_cache`) for high-frequency lookup operations.
- **Session Memory (`app.py`)**: Active battle sessions are bounded using `ActiveBattleStore` with thread-safe LRU eviction to prevent unbounded memory growth.
