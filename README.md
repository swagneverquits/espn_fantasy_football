# Fantasy Football

Tools for collecting live fantasy matchup data from ESPN and Sleeper, storing normalized 30-second snapshots as Parquet objects, and generating compact matchup plots with pandas.

## Project layout

```text
fantasy_football/
  constants.py          Shared paths, API endpoints, column names, and defaults
  config.py             TOML league configuration loading
  storage/              Raw Parquet objects, snapshot pipeline, and DuckDB queries
  scrapers/             Shared lifecycle plus ESPN, Sleeper, and schedule implementations
  analysis/plotting.py   Matchup plotting
config/
  leagues.toml.example  Checked-in configuration template
scripts/run.py           Unified scraping, sync, and analysis entry point
results/
  parquet/              Local Parquet cache used for analysis
  plots/                Generated plots
```

## Setup

```powershell
conda env create -f environment.yml
conda activate espn-fantasy-football
Copy-Item config/leagues.toml.example config/leagues.toml
```

Edit `config/leagues.toml` with the leagues to track. The local file is ignored by Git. League IDs are numeric TOML values.

For local writes, raw `.pq` Parquet objects are saved under `results/parquet`. On the server, set `GCS_BUCKET` and authenticate with Google Application Default Credentials; the scraper uploads each completed object directly to that bucket. DuckDB reads the raw local objects for analysis; no compaction step is required.

## Collect data

Run one scrape:

```powershell
python scripts/run.py scrape espn --league example_league --once
python scripts/run.py scrape sleeper --league-id 123456789012345678 --once
```

Run continuous polling, using the shared 30-second default:

```powershell
python scripts/run.py scrape all
```

Each poll writes one `team_snapshots` object and one `player_snapshots` object per league/week. Metadata objects are written only on the first poll or when their values change. Object paths are partitioned by provider, league, season, week, table, and Unix timestamp.

## Local analysis

Incrementally download new Parquet objects from GCS into the local cache. For plotting, only the team and league tables are needed:

```powershell
python scripts/run.py sync --bucket YOUR_BUCKET --provider espn --league-id 123456789 --season 2026 --week 1 --tables team_snapshots team_metadata league_metadata
```

Generate plots from the local Parquet cache through DuckDB and pandas:

```powershell
python scripts/run.py analyze --provider espn --season 2026 --week 1 --league example_league
```

For Sleeper, use the configured TOML league name and `--provider sleeper`. Plots are written to `results/plots/<season>/<league>/week_<week>/`.


## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football scripts tests
isort fantasy_football scripts tests
```

### Schedule gate

By default, polling is schedule-gated: the scraper starts 15 minutes before each NFL kickoff and remains active for four hours after it. Overlapping windows are merged, and gaps between game windows are left idle. Use `--no-schedule-gate` for continuous polling during debugging; `--once` always bypasses the gate.
