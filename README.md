# ESPN Fantasy Football

Tools for collecting live ESPN Fantasy Football matchup data and generating compact matchup plots.

## Project layout

```text
fantasy_football/
  config.py              Environment, paths, and league IDs
  io.py                  CSV and output path helpers
  espn_scraping/         ESPN JSON API client, parser, scraper, and plotter
  analysis/              Transform, plotting, and report generation workflow
scripts/
  run_api_scraper.py     CLI entry point for API polling
  run_analysis.py        CLI entry point for plot generation
```

Local-only files such as `.env`, generated data, scratch files, caches, and plans are ignored by Git.

## Setup

```powershell
conda env create -f environment.yml
conda activate espn-fantasy-football
```

Configure the private league IDs and ESPN session cookies in `.env`:

```text
ESPN_S2=
ESPN_SWID=
DEFAULT_LEAGUE=
ESPN_LEAGUE_ID_COLLEGE=
ESPN_LEAGUE_ID_HIGH_SCHOOL=
ESPN_LEAGUE_ID_CHARTER=
```

## Run the API scraper

```powershell
python scripts/run_api_scraper.py --league high_school --once
python scripts/run_api_scraper.py --league college --interval 30
```

Snapshots are written to `data/results/<season>/<league>/week_<week>.csv`.

## Generate plots

```powershell
python scripts/run_analysis.py --season 2025 --week 3 --league college
```

Generated plots are written to `data/plots/<season>/<league>/week_<week>/`.

## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football scripts tests
isort fantasy_football scripts tests
```
