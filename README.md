# Fantasy Football

Tools for collecting live fantasy matchup data from ESPN and Sleeper, storing normalized 30-second snapshots as Parquet objects, and generating compact matchup plots with pandas.

## Project layout

```text
fantasy_football/
  constants.py          Shared paths, API endpoints, column names, and defaults
  config.py             Explicit TOML league configuration loading
  storage/              Raw Parquet objects, snapshot pipeline, and DuckDB queries
  scrapers/             Shared provider interface plus ESPN and Sleeper implementations
  schedule/             NFL schedule acquisition, caching, and game windows
  snapshot.py           Shared five-table DataFrame contract
  runtime/              Polling, retries, worker supervision, and heartbeats
  terminal/             Live scraper dashboard and sync progress display
  plotting/             Render matchup figures from loaded DataFrames
config/
  leagues.toml.example  Checked-in configuration template
fantasy_football/cli.py  Unified scraping, sync, and analysis entry point
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

Edit `config/leagues.toml` with the leagues to track. The local file is ignored by Git. League IDs are numeric TOML values. To select another file, put `--config PATH` before the command. CLI help, sync, and scraping a Sleeper league by ID do not require this file.

Local storage is the default and saves raw `.pq` objects under `results/parquet`. On the server, select `--storage gcs`, set `GCS_BUCKET`, and authenticate with Google Application Default Credentials to upload each completed object directly to GCS. DuckDB reads the raw local objects for analysis; no compaction step is required.

## Collect data

Run one scrape:

```powershell
python -m fantasy_football.cli scrape espn --league example_league --once
python -m fantasy_football.cli scrape sleeper --league-id 123456789012345678 --once
```

Run continuous polling locally, using the shared 30-second default:

```powershell
python -m fantasy_football.cli scrape all
```

Use `--storage gcs` with `GCS_BUCKET` set to upload to GCS; use `--storage local` to write only to `results/parquet`.

Each poll writes one `team_snapshots` object and one `player_snapshots` object per league/week. Metadata objects are written only on the first poll or when their values change. Object paths are partitioned by provider, league, season, week, table, and Unix timestamp.

Sleeper checks the current NFL week every two hours and refreshes league/user metadata when the week changes. `scrape all --once` waits for every league to finish successfully; a failed worker stops the run with a nonzero exit code.

Sleeper player IDs are stored as text, including defense abbreviations such as `PHI`. Unavailable Sleeper projections count as zero in both player snapshots and team totals. ESPN player points use actual stats for the current scoring period. If Sleeper's probability formula cannot accept the supplied scores/projections, the snapshot retains scores and stores a missing probability with a warning; it does not substitute a guessed percentage.

Metadata hash state is written atomically and kept separately for local storage and each GCS bucket. Invalid state is rebuilt by writing metadata again. Upgrading from the older shared state files causes one fresh metadata write per league.

## Local analysis

Incrementally download new Parquet objects from GCS into the local cache. For plotting, only the team and league tables are needed:

Downloads use temporary files and are published only after completion. Existing files with an unexpected size are downloaded again.

```powershell
python -m fantasy_football.cli sync --bucket YOUR_BUCKET --provider espn --league-id 123456789 --season 2026 --week 1 --tables team_snapshots team_metadata league_metadata
```

Generate plots from the local Parquet cache through DuckDB and pandas:

```powershell
python -m fantasy_football.cli analyze --provider espn --season 2026 --week 1 --league example_league
```

For Sleeper, use the configured TOML league name and `--provider sleeper`. Plots are written to `results/plots/<season>/<league>/week_<week>/`.


## Checks

```powershell
python -m unittest discover -s tests -v
black fantasy_football tests
isort fantasy_football tests
```

### Schedule gate

By default, polling is schedule-gated: the scraper starts 15 minutes before each NFL kickoff and remains active for four hours after it. Overlapping windows are merged, and gaps between game windows are left idle. Use `--no-schedule-gate` for continuous polling during debugging; `--once` always bypasses the gate.

## Code boundaries

Each provider implements `Scraper.fetch_snapshot() -> Snapshot`. Its parser produces the five normalized DataFrames using the shared schema in `snapshot.py`. Each provider keeps HTTP requests and acquisition in `scraper.py`, and response normalization in `parser.py`. Sleeper's probability calculation remains in `win_probability.py`.

`Poller` handles timing and retries, while `run_all` supervises league workers. The writer accepts a `Snapshot` and handles Parquet persistence and metadata change detection. These changes preserve the existing object paths and persisted columns.

DuckDB returns the stored snake_case columns plus team/league names. Plotting accepts those DataFrames directly and converts Unix timestamps to Eastern Time for display. Configuration and database queries are handled by the CLI, outside rendering.

Package organization:

- `runtime/`: polling/retries, worker supervision, and heartbeat persistence.
- `terminal/`: the scraper dashboard and local sync display.
- `schedule/`: NFL schedule acquisition, shared caching, and game windows.
- `scrapers/`: provider acquisition and normalization.
- `storage/`: snapshot persistence, incremental sync, and DuckDB queries.
- `plotting/`: matchup preparation (`matchups.py`), shared timeline geometry (`timeline.py`), and PNG rendering (`renderer.py`).

The root retains the CLI, configuration, shared constants, and snapshot schema. CLI commands and persisted data formats are unchanged. Tests cover each responsibility independently.

Storage modules are organized by responsibility: `writer.py` saves snapshots and metadata state, `parquet.py` serializes and publishes objects and defines their shared partition paths, `sync.py` downloads them, and `duckdb.py` queries them. The CLI resolves storage environment settings. Local writes stage files on the destination filesystem before publishing them atomically.

Plot panels follow collection windows inferred from timestamp gaps longer than 30 minutes (adjustable via `window_gap_seconds` in the plotting functions). Midnight does not split a window; labels use the window's starting date. Long collection outages will also create a panel break.

The shared schedule cache uses OS-managed locks, released when the owner exits. The lock file can remain on disk without indicating ownership. Waiting workers only accept fresh cached schedules.

Missing ESPN probabilities retain the team's score. Unavailable or non-finite Sleeper starter projections default to zero, allowing team totals and probabilities to be calculated from the remaining projections. Matching the weekly projection inputs to Sleeper's live UI has not been verified: the historical stats endpoint returned HTTP 403 during the latest check. The current inputs must not be treated as confirmed live UI projections.

## All-league local updates

Use `--all` with sync and analyze to select leagues from `leagues.toml`. Add `--provider espn` or `--provider sleeper` to limit the selection. Season and week remain explicit; `--all` selects leagues, not historical weeks.

```powershell
python -m fantasy_football.cli sync --all --bucket YOUR_BUCKET --season 2026 --week 1 --tables team_snapshots team_metadata league_metadata
python -m fantasy_football.cli analyze --all --season 2026 --week 1
```

Sync runs leagues concurrently (up to eight), preserves incremental downloads, and reports a nonzero exit status if any league fails. Other leagues finish even if one fails. Plotting runs sequentially and skips leagues without local snapshots; it returns nonzero for rendering failures or if no plots were generated. All-league plots go under `results/plots/<season>/<provider>/<league>/week_<week>/` to avoid name collisions across providers. Single-league commands keep their existing output paths.

Scraping all leagues continues to use `scrape all`.

## Remote scraper dashboard

After deploying the updated image, open the live dashboard over SSH:

```bash
sudo docker compose exec scraper python -m fantasy_football.cli status --watch
```

One row per configured league shows worker state, last scrape result, completed-at time in ET, and failed scrape count. A single approximate uptime above the table uses the longest-running healthy worker. Success means both fetch and persistence completed; partial uploads are failures. Uptime and error counts reset when a worker restarts. Idle is normal outside game windows. Heartbeats older than 20 seconds show stale/offline and are excluded from the uptime summary. Last-success timestamps remain in the status files, but are not displayed as a column.

Ctrl+C closes only the dashboard. Omit `--watch` for a single table. Status files are ephemeral local files inside the container, not uploaded to GCS. Existing Docker logs remain unchanged:

```bash
sudo docker compose logs -f --tail=100 scraper
```

While every worker is healthy and idle, the dashboard shows upcoming NFL windows above the league table, including week, game count, and opening/closing times in ET. It hides that schedule during active polling. The dashboard only reads the shared schedule cache; it never makes schedule API calls.

Matchup plots are rendered as phone-oriented portrait PNGs. The Win probability panel uses a linear tug-of-war scale around Even, with independent space for each team's observed advantage; Points and Win probability share the same compressed activity-window timeline.
