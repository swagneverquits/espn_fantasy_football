"""Prepare and generate compact matchup plots from Parquet snapshots."""

import textwrap
from collections.abc import Iterable
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from fantasy_football.constants import MATCHUP_ID_COL, TEAM_ID_COL, TIMESTAMP_COL
from fantasy_football.plotting.constants import (
    ANNOTATION_SIZE,
    AXIS_TITLE_SIZE,
    DATE_SIZE,
    DEFAULT_GAME_DAYS,
    EDGE_LIMIT,
    EDGE_TICK_LABELS,
    EDGE_TICKS,
    EMOJI_FONT,
    HOUR_SIZE,
    LEAGUE_NAME_COL,
    MAIN_TITLE_SIZE,
    PROJECTED_COL,
    SCORE_COL,
    TEAM_COL,
    TEAM_COLORS,
    TICK_SIZE,
    WIN_CHANCE_COL,
)


def plot_matchup(
    matchup_df: pd.DataFrame,
    *,
    league_name: str,
    week: int | str,
    matchup: int | str,
    savepath: str | Path,
    days: Iterable[str] = DEFAULT_GAME_DAYS,
) -> Path:
    """Save a compact mirrored-probability and points plot for one matchup."""
    # Normalize the input and identify the two teams and game-day windows.
    plt.rcParams["font.family"] = "Segoe UI"
    data = matchup_df.copy()
    if pd.api.types.is_numeric_dtype(data[TIMESTAMP_COL]):
        data[TIMESTAMP_COL] = pd.to_datetime(
            data[TIMESTAMP_COL], unit="s", utc=True
        ).dt.tz_convert("America/New_York")
    else:
        data[TIMESTAMP_COL] = pd.to_datetime(data[TIMESTAMP_COL])
    data = data.sort_values(TIMESTAMP_COL)
    team_ids = list(data[TEAM_ID_COL].drop_duplicates())
    teams = [
        data.loc[data[TEAM_ID_COL].eq(team_id), TEAM_COL].iloc[-1]
        for team_id in team_ids
    ]
    if len(teams) != 2:
        raise ValueError("matchup_df must contain exactly two teams")
    day_names = list(days)
    day_dates = {day: _date_for_day(data, day) for day in day_names}
    widths = [_day_width(data, day_dates[day]) for day in day_names]
    frames = [
        data[data[TEAM_ID_COL].eq(team_id)].set_index(TIMESTAMP_COL)
        for team_id in team_ids
    ]
    # Create aligned Edge and Points panels for each game day.
    fig, axes = plt.subplots(
        2,
        len(day_names),
        figsize=(10, 5),
        sharey="row",
        sharex="col",
        squeeze=False,
        gridspec_kw={"height_ratios": [1.4, 1], "width_ratios": widths},
    )
    fig.subplots_adjust(
        left=0.08, right=0.99, top=0.86, bottom=0.18, wspace=0.04, hspace=0.18
    )
    fig.suptitle(
        f"{league_name} | Week {week} | Matchup {matchup}",
        fontsize=MAIN_TITLE_SIZE,
        fontweight="bold",
        x=0.08,
        y=0.97,
        ha="left",
    )
    # Render each day independently so discontinuities remain visible.
    for col, day in enumerate(day_names):
        date = day_dates[day]
        edge_ax, points_ax = axes[0, col], axes[1, col]
        edge_data = frames[0][frames[0].index.date == date]
        if not edge_data.empty:
            edge = (edge_data[WIN_CHANCE_COL] - 0.5) * 100
            x = edge_data.index
            edge_ax.fill_between(
                x, 0, edge, where=edge >= 0, color=TEAM_COLORS[0], alpha=0.85
            )
            edge_ax.fill_between(
                x, 0, edge, where=edge < 0, color=TEAM_COLORS[1], alpha=0.85
            )
            edge_ax.plot(x, edge, color="#222222", lw=1.8)
            edge_ax.axhline(0, color="#222222", ls="--", lw=1.0, zorder=3)
        for frame, color in zip(frames, TEAM_COLORS):
            day_data = frame[frame.index.date == date]
            if not day_data.empty:
                points_ax.plot(day_data.index, day_data[SCORE_COL], color=color, lw=2.0)
                points_ax.plot(
                    day_data.index,
                    day_data[PROJECTED_COL],
                    color=color,
                    lw=1.1,
                    ls="--",
                    alpha=0.8,
                )
        # Apply shared scales, grids, spines, and date-axis formatting.
        edge_ax.set_title("")
        edge_ax.set_ylim(-EDGE_LIMIT, EDGE_LIMIT)
        edge_ax.set_yticks(EDGE_TICKS, labels=EDGE_TICK_LABELS)
        edge_ax.grid(axis="y", color="#d8d8d8", lw=0.7)
        edge_ax.spines[["top", "right", "left"]].set_visible(False)
        edge_ax.spines["bottom"].set_linewidth(0.6)
        edge_ax.tick_params(axis="y", length=0, labelsize=TICK_SIZE)
        points_ax.set_ylim(bottom=0)
        points_ax.grid(axis="y", color="#e0e0e0", lw=0.7)
        points_ax.spines[["top", "right", "left"]].set_visible(False)
        points_ax.spines["bottom"].set_linewidth(0.6)
        points_ax.tick_params(axis="y", labelsize=TICK_SIZE)
        if col:
            points_ax.tick_params(axis="y", left=False, labelleft=False)
        points_ax.xaxis.set_major_locator(
            mdates.HourLocator(interval=3, tz="America/New_York")
        )
        points_ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%I %p", tz="America/New_York")
        )
        points_ax.tick_params(axis="x", labelsize=HOUR_SIZE, pad=2)
        points_ax.set_xlabel(
            f"{day} {_format_date(date)}",
            fontsize=DATE_SIZE,
            fontweight="medium",
            labelpad=6,
        )
        day_data = data[data[TIMESTAMP_COL].dt.date == date]
        if not day_data.empty:
            edge_ax.set_xlim(
                day_data[TIMESTAMP_COL].min(), day_data[TIMESTAMP_COL].max()
            )
            points_ax.set_xlim(
                day_data[TIMESTAMP_COL].min(), day_data[TIMESTAMP_COL].max()
            )
        edge_ax.grid(axis="x", color="#ededed", lw=0.5)
        points_ax.grid(axis="x", color="#ededed", lw=0.5)
    # Add matchup-level team labels and the realized/projected legend.
    fig.text(
        0.5,
        0.80,
        f"\u2191 {textwrap.fill(teams[0], 28)} \u2191",
        color=TEAM_COLORS[0],
        fontsize=TICK_SIZE,
        fontweight="bold",
        fontproperties=EMOJI_FONT,
        va="center",
        ha="center",
        linespacing=1.05,
    )
    # Add matchup-level team labels and the realized/projected legend.
    fig.text(
        0.5,
        0.53,
        f"\u2193 {textwrap.fill(teams[1], 28)} \u2193",
        color=TEAM_COLORS[1],
        fontsize=TICK_SIZE,
        fontweight="bold",
        fontproperties=EMOJI_FONT,
        va="center",
        ha="center",
        linespacing=1.05,
    )
    # Add matchup-level team labels and the realized/projected legend.
    fig.text(
        0.5,
        0.055,
        "solid = realized  \u00b7  dashed = projected",
        fontsize=ANNOTATION_SIZE,
        ha="center",
        va="center",
    )
    # Label the shared y-axes and save the finished figure.
    axes[0, 0].set_ylabel("Edge", fontsize=AXIS_TITLE_SIZE, fontweight="bold")
    axes[1, 0].set_ylabel("Points", fontsize=AXIS_TITLE_SIZE, fontweight="bold")
    output = Path(savepath)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _date_for_day(data: pd.DataFrame, day: str):
    matches = data[data[TIMESTAMP_COL].dt.day_name().eq(day)]
    return matches[TIMESTAMP_COL].dt.date.iloc[0] if not matches.empty else None


def _day_width(data: pd.DataFrame, date) -> float:
    if date is None:
        return 1.0
    day = data[data[TIMESTAMP_COL].dt.date == date]
    return (
        max((day[TIMESTAMP_COL].max() - day[TIMESTAMP_COL].min()).total_seconds(), 1.0)
        if not day.empty
        else 1.0
    )


def _format_date(date) -> str:
    return f"{date.month}/{date.day}" if date is not None else ""


def normalize_team_names(data: pd.DataFrame) -> pd.DataFrame:
    """Use each team's latest name without relying on row ordering or display names."""
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
) -> list[Path]:
    """Render every matchup from already loaded data; no configuration or queries."""
    if data.empty:
        return []
    data = normalize_team_names(data)
    if data[LEAGUE_NAME_COL].notna().any():
        league_name = data[LEAGUE_NAME_COL].dropna().iloc[-1]
    dates = pd.to_datetime(data[TIMESTAMP_COL], unit="s", utc=True).dt.tz_convert(
        "America/New_York"
    )
    paths = []
    for number, (matchup_id, matchup) in enumerate(
        data.groupby(MATCHUP_ID_COL, sort=True), start=1
    ):
        days = list(dates.loc[matchup.index].dt.day_name().drop_duplicates())
        paths.append(
            plot_matchup(
                matchup,
                league_name=league_name,
                week=week,
                matchup=matchup_id,
                days=days,
                savepath=Path(output_dir) / f"matchup{number}.png",
            )
        )
    return paths
