"""Prepare and generate portrait matchup plots from Parquet snapshots."""

from pathlib import Path

import pandas as pd

from fantasy_football.constants import MATCHUP_ID_COL, TEAM_ID_COL, TIMESTAMP_COL
from fantasy_football.plotting.constants import LEAGUE_NAME_COL, TEAM_COL


def _game_windows(
    data: pd.DataFrame, gap_seconds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Infer independent collection windows from gaps in the timestamps."""
    if gap_seconds <= 0:
        raise ValueError("window_gap_seconds must be positive")
    times = data[TIMESTAMP_COL].drop_duplicates().sort_values()
    groups = times.diff().dt.total_seconds().gt(gap_seconds).cumsum()
    grouped = list(times.groupby(groups))
    if len(grouped) > 1 and len(grouped[-1][1]) == 1 and len(grouped[-2][1]) > 1:
        grouped.pop()
    return [(group.iloc[0], group.iloc[-1]) for _, group in grouped]


def normalize_team_names(data: pd.DataFrame) -> pd.DataFrame:
    """Use each team's latest name without relying on row ordering."""
    data = data.sort_values(TIMESTAMP_COL).copy()
    keys = [MATCHUP_ID_COL, TEAM_ID_COL]
    data[TEAM_COL] = data.groupby(keys)[TEAM_COL].transform("last")
    return data


def generate_matchup_plots(
    data: pd.DataFrame,
    *,
    week: int | str,
    output_dir: str | Path,
    league_name: str,
    window_gap_seconds: int = 30 * 60,
    season: int | None = None,
) -> list[Path]:
    """Render every matchup as a phone-oriented portrait PNG."""
    if data.empty:
        return []

    from .portrait import plot_matchup_portrait

    data = normalize_team_names(data)
    if data[LEAGUE_NAME_COL].notna().any():
        league_name = data[LEAGUE_NAME_COL].dropna().iloc[-1]

    paths = []
    for number, (matchup_id, matchup) in enumerate(
        data.groupby(MATCHUP_ID_COL, sort=True), start=1
    ):
        paths.append(
            plot_matchup_portrait(
                matchup,
                league_name=league_name,
                week=week,
                matchup=matchup_id,
                window_gap_seconds=window_gap_seconds,
                season=season,
                savepath=Path(output_dir) / f"matchup{number}.png",
            )
        )
    return paths
