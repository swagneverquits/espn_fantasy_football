# Fantasy Football

Tools for collecting live fantasy matchup data from ESPN and Sleeper, storing normalized 30-second snapshots as Parquet objects, and generating compact matchup plots with pandas.

## Project layout

```text
fantasy_football/
  constants.py          Shared paths, API endpoints, column names, and defaults
  config.py             TOML league configuration loading
  normalization.py      Provider-specific player normalization
  storage/              Parquet objects, snapshot pipeline, compaction, and sync
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

For local writes, `.pq` Parquet objects are saved under `results/parquet`. On the server, set `GCS_BUCKET` and authenticate with Google Application Default Credentials; the scraper uploads each completed object directly to that bucket.

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

Download one league/week from GCS into the local Parquet cache:

```powershell
python scripts/run.py sync --bucket YOUR_BUCKET --provider espn --league-id 123456789 --season 2026 --week 1
```

Generate plots from local Parquet with pandas:

```powershell
python scripts/run.py analyze --provider espn --season 2026 --week 1 --league example_league
```

For Sleeper, use the configured TOML league name and `--provider sleeper`. Plots are written to `results/plots/<season>/<league>/week_<week>/`.

Compact a completed week in GCS. The five compacted `.pq` files are written directly under the week prefix; raw polling objects are retained:

```powershell
python scripts/run.py compact --bucket YOUR_BUCKET --provider espn --league-id YOUR_LEAGUE_ID --season 2026 --week 1
```

## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football scripts tests
isort fantasy_football scripts tests
```

### Schedule gate

By default, polling is schedule-gated: the scraper starts 15 minutes before each NFL kickoff and remains active for four hours after it. Overlapping windows are merged, and gaps between game windows are left idle. Use --no-schedule-gate for continuous polling during debugging; --once always bypasses the gate.
