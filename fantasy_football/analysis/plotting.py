"""Prepare and generate compact matchup plots from SQLite snapshots."""

import textwrap
from collections.abc import Iterable
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties

from fantasy_football.analysis.constants import (
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
    MATCHUP_COL,
    PROJECTED_COL,
    SCORE_COL,
    TEAM_COL,
    TEAM_COLORS,
    TICK_SIZE,
    TIME_COL,
    WIN_CHANCE_COL,
)
from fantasy_football.config import ESPN_LEAGUES, SLEEPER_LEAGUES
from fantasy_football.constants import PARQUET_DIR, PLOTS_DIR
from fantasy_football.storage.pipeline import load_matchup_results_from_parquet


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
    data[TIME_COL] = pd.to_datetime(data[TIME_COL])
    data = data.sort_values("time")
    teams = list(data[TEAM_COL].drop_duplicates())[:2]
    if len(teams) != 2:
        raise ValueError("matchup_df must contain exactly two teams")
    day_names = list(days)
    day_dates = {day: _date_for_day(data, day) for day in day_names}
    widths = [_day_width(data, day_dates[day]) for day in day_names]
    frames = [data[data[TEAM_COL].eq(team)].set_index("time") for team in teams]
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
                points_ax.plot(day_data.index, day_data["Score"], color=color, lw=2.0)
                points_ax.plot(
                    day_data.index,
                    day_data["Projected"],
                    color=color,
                    lw=1.1,
                    ls="--",
                    alpha=0.8,
                )
        # Apply shared scales, grids, spines, and date-axis formatting.
        edge_ax.set_title("")
        edge_ax.set_ylim(-EDGE_LIMIT, EDGE_LIMIT)
        edge_ax.set_yticks(
            [-50, -25, 0, 25, 50], labels=["100%", "75%", "Even", "75%", "100%"]
        )
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
        points_ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        points_ax.xaxis.set_major_formatter(mdates.DateFormatter("%I %p"))
        points_ax.tick_params(axis="x", labelsize=HOUR_SIZE, pad=2)
        points_ax.set_xlabel(
            f"{day} {_format_date(date)}",
            fontsize=DATE_SIZE,
            fontweight="medium",
            labelpad=6,
        )
        day_data = data[data[TIME_COL].dt.date == date]
        if not day_data.empty:
            edge_ax.set_xlim(day_data[TIME_COL].min(), day_data[TIME_COL].max())
            points_ax.set_xlim(day_data[TIME_COL].min(), day_data[TIME_COL].max())
        edge_ax.grid(axis="x", color="#ededed", lw=0.5)
        points_ax.grid(axis="x", color="#ededed", lw=0.5)
    # Add matchup-level team labels and the realized/projected legend.
    fig.text(
        0.5,
        0.80,
        f"↑ {textwrap.fill(teams[0], 28)} ↑",
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
        f"↓ {textwrap.fill(teams[1], 28)} ↓",
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
        "solid = realized  ·  dashed = projected",
        color="#555555",
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
    matches = data[data[TIME_COL].dt.day_name().eq(day)]
    return matches["time"].dt.date.iloc[0] if not matches.empty else None


def _day_width(data: pd.DataFrame, date) -> float:
    if date is None:
        return 1.0
    day = data[data[TIME_COL].dt.date == date]
    return (
        max((day["time"].max() - day["time"].min()).total_seconds(), 1.0)
        if not day.empty
        else 1.0
    )


def _format_date(date) -> str:
    return f"{date.month}/{date.day}" if date is not None else ""


def normalize_team_names(matchup_df: pd.DataFrame) -> pd.DataFrame:
    """Use the latest name for each matchup slot throughout the plot."""
    updated = []
    for _, matchup in matchup_df.sort_index().groupby("Matchup", group_keys=False):
        matchup = matchup.reset_index()
        matchup["slot"] = matchup.groupby(TIME_COL).cumcount()
        latest_names = matchup.groupby("slot").tail(1).set_index("slot")[TEAM_COL]
        matchup[TEAM_COL] = matchup["slot"].map(latest_names)
        updated.append(matchup.set_index(["time", "team"]))
    return pd.concat(updated).sort_index()


def generate_matchup_plots(
    season: int, week: int, league: str, provider: str = "espn"
) -> list[Path]:
    """Generate one common-format plot per matchup in a league week."""
    leagues = ESPN_LEAGUES if provider == "espn" else SLEEPER_LEAGUES
    if league not in leagues:
        valid_leagues = ", ".join(sorted(leagues))
        raise ValueError(f"Unknown league '{league}'. Expected one of: {valid_leagues}")

    output_dir = PLOTS_DIR / str(season) / league / f"week_{week}"
    data = normalize_team_names(
        load_matchup_results_from_parquet(
            PARQUET_DIR,
            provider=provider,
            league_id=leagues[league],
            season=season,
            matchup_period=week,
        )
    ).reset_index()
    matchup_ids = sorted(data[MATCHUP_COL].dropna().unique())
    league_name = (
        data[LEAGUE_NAME_COL].dropna().iloc[0]
        if data[LEAGUE_NAME_COL].notna().any()
        else league
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for matchup_number, matchup_id in enumerate(matchup_ids, start=1):
        matchup = data[data[MATCHUP_COL].eq(matchup_id)].copy()
        days = list(pd.to_datetime(matchup[TIME_COL]).dt.day_name().drop_duplicates())
        path = output_dir / f"matchup{matchup_number}.png"
        plot_matchup(
            matchup,
            league_name=league_name,
            week=week,
            matchup=matchup_number,
            days=days,
            savepath=path,
        )
        paths.append(path)
    return paths
