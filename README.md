# Fantasy Football

Tools for collecting live fantasy matchup data from ESPN and Sleeper, storing normalized snapshots in SQLite, and generating compact matchup plots.

## Project layout

```text
fantasy_football/
  constants.py          Shared paths, table names, column names, and defaults
  config.py             TOML league configuration loading
  storage.py            SQLite schema, persistence, reads, and CSV export
  scrapers/
    base.py             Shared scraper lifecycle and polling loop
    espn/               ESPN client, parser, and scraper
    sleeper/            Sleeper client, parser, and scraper
  analysis/             Matchup normalization, plotting, and reports
config/
  leagues.toml.example  Checked-in configuration template
scripts/
  run_api_scraper.py    ESPN polling entry point
  run_sleeper_scraper.py Sleeper polling entry point
  run_analysis.py       ESPN plot-generation entry point
results/
  data/                 SQLite database and archived legacy data
  plots/                Generated plots
```

## Setup

```powershell
conda env create -f environment.yml
conda activate espn-fantasy-football
Copy-Item config/leagues.toml.example config/leagues.toml
```

Edit `config/leagues.toml` with the leagues to track. The local file is ignored by Git. League IDs are numeric TOML values:

```toml
[espn]
college = 1850396491
high_school = 1012938436

[sleeper]
football_jawn_dynasty = 1313543921472651264
```

## Collect data

Run one scrape:

```powershell
python scripts/run_api_scraper.py --league high_school --once
python scripts/run_sleeper_scraper.py --league-id 1313543921472651264 --once
```

Run continuous polling, using the shared 30-second default:

```powershell
python scripts/run_api_scraper.py --league high_school
python scripts/run_sleeper_scraper.py --league-id 1313543921472651264
```

The canonical database is `results/data/fantasy_football.sqlite`. The live pipeline writes directly to SQLite; CSVs are only produced explicitly for inspection/export.

The database contains:

- `league_metadata` — league identity and names
- `team_metadata` — weekly team names and logos
- `player_metadata` — player names and positions
- `team_snapshots` — live scores, projections, and win probabilities
- `player_snapshots` — live player points and projections

Run every league configured in `config/leagues.toml` in parallel:

```powershell
python scripts/run_all_scrapers.py
python scripts/run_all_scrapers.py --once
```
## Generate plots

The current report command reads from SQLite and supports configured ESPN leagues:

```powershell
python scripts/run_analysis.py --season 2026 --week 1 --league high_school
```

Plots are written to `results/plots/<season>/<league>/week_<week>/`.

## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football scripts tests
isort fantasy_football scripts tests
```