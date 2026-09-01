# Fantasy Football

Tools for collecting live fantasy matchup data from ESPN and Sleeper, storing normalized snapshots in SQLite, and generating compact matchup plots.

## Project layout

```text
fantasy_football/
  constants.py          Shared paths, table names, column names, and defaults
  config.py             TOML league configuration loading
  storage.py            Shared SQLite schema and persistence
  scrapers/
    base.py             Provider scraper lifecycle
    espn/               ESPN client, parser, and scraper
    sleeper/            Sleeper client, parser, and scraper
  analysis/             Common normalization, plotting, and reports
config/
  leagues.toml.example  Checked-in configuration template
scripts/
  run_api_scraper.py    ESPN polling entry point
  run_sleeper_scraper.py Sleeper polling entry point
  run_analysis.py       Plot generation entry point
results/
  data/                 Generated SQLite database and archived data
  plots/                Generated plots
```

## Setup

```powershell
conda env create -f environment.yml
conda activate espn-fantasy-football
Copy-Item config/leagues.toml.example config/leagues.toml
```

Edit `config/leagues.toml` with the leagues to track. It is local-only and ignored by Git.

## Run scrapers

```powershell
python scripts/run_api_scraper.py --league high_school --once
python scripts/run_sleeper_scraper.py --league-id 1313543921472651264 --once
```

The canonical database is written to `results/data/fantasy_football.sqlite`.

## Generate plots

```powershell
python scripts/run_analysis.py --season 2026 --week 1 --league high_school
```

Generated plots are written to `results/plots/<season>/<league>/week_<week>/`.

## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football scripts tests
isort fantasy_football scripts tests
```