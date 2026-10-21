# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current scope

This is a Python research project for historical, daily precipitation forecasting and a minimal FastAPI API skeleton. `docs/architecture-v1.md` and `docs/docker-deployment-plan.md` describe a larger warning/approval system with a Vue frontend, MySQL 8.4, Redis 8.10.2, and Docker Compose on an Ubuntu 26.04 VM; do not treat those planned components as implemented or their deployment instructions as verified.

## Commands (from the project root on the Ubuntu VM)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python backend/fusion.py --site 武汉 --lat 30.5928 --lon 114.3055 --start 2024-02-01 --end 2026-09-30 --threshold 25
python backend/pooled.py --out data/results/pooled.json
python backend/summarize.py
```

The experiment commands above are documented in `docs/data-and-method.md`, which also lists coverage, skill-probe, and single-source evaluation commands. They may access external data on cache misses and write results under `data/`. The API's local launch command is `python3 -m uvicorn backend.app.main:app --reload`, but it has not been verified; set `APP_SECRET_KEY` and `DATABASE_URL` (MySQL/PyMySQL URL) first, as `backend/app/db.py` initializes its engine when imported. Ubuntu 26.04 requires the `python3-venv` package for the virtual environment.

There is no configured build or lint task and no existing test suite or pytest configuration. Although `pytest` is in `requirements.txt`, there is no project test command or current single test to run. If pytest tests are added, a conventional single-test invocation is `python3 -m pytest path/to/test_file.py::test_name`.

## Architecture and experimental constraints

- `backend/ingest.py` fetches historical Open-Meteo forecasts and ERA5 labels, caching requests in `data/cache/`; `backend/dataset.py` aggregates complete UTC days. `backend/evaluate.py` and `backend/fusion.py` compare model strategies, while `backend/pooled.py` evaluates the fixed baseline and four-model equal-weight ensemble across nine cities. `data/results/` holds experiment outputs; `backend/observation_eval.py` separately compares against NOAA GHCN-Daily station observations.
- Preserve the comparison protocol in `docs/data-and-method.md`: forecasts have a fixed 24-hour lead; ERA5 is a **proxy label**, not a station measurement; years 2024/2025/2026 are training/validation/test. The main comparison is ECMWF IFS versus an equal-weight ECMWF/GFS/ICON/GEM ensemble on the same samples. GHCN station observations are an independent, coverage-limited cross-check, not a replacement for the nine-city labels.
- `backend/app/main.py` currently exposes only `/health` and `/health/db`. `backend/app/config.py` loads required application and database settings; `backend/app/db.py` sets up the SQLAlchemy engine and sessions. `backend/app/models.py` and `backend/migrations/` define the intended persistence schema, but the full data-import, warning-review, and audit API flows are not yet present.
