import argparse
import logging
from pathlib import Path

import pandas as pd

from fantasy_football.analysis.plots import plot_matchup
from fantasy_football.analysis.transform import normalize_team_names
from fantasy_football.config import LEAGUE_IDS
from fantasy_football.io import get_plots_dir, load_results

DEFAULT_SEASON = 2025
DEFAULT_WEEK = 3
DEFAULT_LEAGUE = "college"


def generate_matchup_plots(season: int, week: int, league: str) -> list[Path]:
    """Generate common-format matchup plots for a collected snapshot file."""
    if league not in LEAGUE_IDS:
        valid_leagues = ", ".join(sorted(LEAGUE_IDS))
        raise ValueError(f"Unknown league '{league}'. Expected one of: {valid_leagues}")

    plots_path = get_plots_dir(season, week, league)
    df = normalize_team_names(load_results(season, week, league)).reset_index()
    num_matchups = int(df["Matchup"].max()) + 1
    saved_paths = []
    for matchup in range(num_matchups):
        matchup_df = df[df["Matchup"].eq(matchup)].copy()
        days = list(pd.to_datetime(matchup_df["time"]).dt.day_name().drop_duplicates())
        savepath = plots_path / f"matchup{matchup}.png"
        plot_matchup(
            matchup_df,
            league_name=league,
            week=week,
            matchup=matchup + 1,
            days=days,
            savepath=savepath,
        )
        saved_paths.append(savepath)
    return saved_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fantasy matchup plots.")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--week", type=int, default=DEFAULT_WEEK)
    parser.add_argument("--league", choices=sorted(LEAGUE_IDS), default=DEFAULT_LEAGUE)
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
