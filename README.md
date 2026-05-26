# ESPN Fantasy Football

Tools for collecting live ESPN fantasy football matchup data and generating matchup plots from the collected CSV snapshots.

## Project Layout

```text
fantasy_football/
  config.py              Environment, paths, and league IDs
  io.py                  CSV and output path helpers
  scraper.py             Main live scraping workflow
  analysis/              Transform, plotting, and report generation workflow
  scraping/              Browser setup and ESPN scraping helpers
scripts/
  run_scraper.py         CLI entry point for live scraping
  run_analysis.py        CLI entry point for plot generation
data/
  raw/                   Optional raw scraped data, ignored by Git
  processed/             Optional cleaned analysis data, ignored by Git
  results/               Generated CSV snapshots, ignored by Git
  plots/                 Generated matchup plots, ignored by Git
```

Local-only files such as `.env`, `data/`, page dumps, scratch files, caches, and plans are ignored by Git.

## Setup

Create the Conda environment:

```powershell
conda env create -f environment.yml
conda activate espn-fantasy-football
```

Copy `.env.example` to `.env` and fill in the local values:

```text
ESPN_EMAIL=
ESPN_PASSWORD=
CHROMEDRIVER_PATH=
DEFAULT_LEAGUE=
ESPN_LEAGUE_ID_COLLEGE=
ESPN_LEAGUE_ID_HIGH_SCHOOL=
ESPN_LEAGUE_ID_CHARTER=
```

`ESPN_EMAIL` and `ESPN_PASSWORD` are required for ESPN login. The league IDs are private ESPN fantasy league identifiers and should stay in `.env`.

Chrome must be installed locally for Selenium scraping. Selenium 4.6+ can usually manage ChromeDriver automatically; set `CHROMEDRIVER_PATH` only if your machine needs an explicit driver path.

Verify the environment:

```powershell
python -m py_compile fantasy_football\config.py fantasy_football\scraper.py fantasy_football\analysis\reports.py scripts\run_scraper.py scripts\run_analysis.py
python scripts\run_analysis.py --help
```

## Run The Scraper

```powershell
python scripts/run_scraper.py
```

The scraper opens Chrome, logs into ESPN, detects the active NFL week, navigates to FantasyCast, and appends matchup snapshots to:

```text
data/results/<season>/<league>/week_<week>.csv
```

`data/results/` is the current scraper output location. `data/raw/` and `data/processed/` are reserved for a future data pipeline split.

Current caveat: the scraper league is hardcoded in `fantasy_football/scraper.py`.

## Generate Plots

```powershell
python scripts/run_analysis.py --season 2025 --week 3 --league college
```

The analysis workflow loads a collected CSV, normalizes team names, and writes matchup plots to:

```text
data/plots/<season>/<league>/week_<week>/
```

The same workflow can also be run as a module:

```powershell
python -m fantasy_football.analysis --season 2025 --week 3 --league college
```

## Notes

- Do not commit `.env`; it contains ESPN credentials and private league IDs.
- `requirements.txt` currently reflects an older local environment; prefer `environment.yml` for fresh setup.
- Generated data and plots are intentionally excluded from Git.
