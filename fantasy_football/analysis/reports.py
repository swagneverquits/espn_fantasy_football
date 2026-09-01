"""Generate matchup plots from the canonical SQLite database."""

import argparse
import logging
from pathlib import Path

import pandas as pd

from fantasy_football.analysis.plots import plot_matchup
from fantasy_football.analysis.transform import normalize_team_names
from fantasy_football.config import LEAGUE_IDS
from fantasy_football.constants import PLOTS_DIR, SQLITE_PATH
from fantasy_football.storage import load_matchup_results


def generate_matchup_plots(season: int, week: int, league: str) -> list[Path]:
    """Generate one common-format plot per matchup in a league week."""
    if league not in LEAGUE_IDS:
        valid_leagues = ", ".join(sorted(LEAGUE_IDS))
        raise ValueError(f"Unknown league '{league}'. Expected one of: {valid_leagues}")

    plots_path = PLOTS_DIR / str(season) / league / f"week_{week}"
    plots_path.mkdir(parents=True, exist_ok=True)
    df = normalize_team_names(
        load_matchup_results(
            SQLITE_PATH,
            provider="espn",
            league_id=LEAGUE_IDS[league],
            season=season,
            matchup_period=week,
        )
    ).reset_index()
    matchup_ids = sorted(df["Matchup"].dropna().unique())
    league_name = (
        df["league_name"].dropna().iloc[0]
        if df["league_name"].notna().any()
        else league
    )

    saved_paths = []
    for matchup_number, matchup_id in enumerate(matchup_ids, start=1):
        matchup_df = df[df["Matchup"].eq(matchup_id)].copy()
        days = list(pd.to_datetime(matchup_df["time"]).dt.day_name().drop_duplicates())
        savepath = plots_path / f"matchup{matchup_number}.png"
        plot_matchup(
            matchup_df,
            league_name=league_name,
            week=week,
            matchup=matchup_number,
            days=days,
            savepath=savepath,
        )
        saved_paths.append(savepath)
    return saved_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fantasy matchup plots.")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--league", choices=sorted(LEAGUE_IDS), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        saved_paths = generate_matchup_plots(args.season, args.week, args.league)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Analysis input error: {exc}") from exc
    logging.info("Generated %d plot(s)", len(saved_paths))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    main()
