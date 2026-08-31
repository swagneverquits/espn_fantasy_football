"""Compact matchup plots for API snapshot data."""

import textwrap
from collections.abc import Iterable
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties

TEAM_COLORS = ("#d49a00", "#5b2a86")
EMOJI_FONT = FontProperties(fname=r"C:\Windows\Fonts\seguiemj.ttf")
MAIN_TITLE_SIZE, AXIS_TITLE_SIZE = 17, 12.5
DATE_SIZE, TICK_SIZE, HOUR_SIZE = 11.5, 9.5, 9


def plot_matchup(
    matchup_df: pd.DataFrame,
    *,
    league_name: str,
    week: int | str,
    matchup: int | str,
    savepath: str | Path,
    days: Iterable[str] = ("Thursday", "Sunday", "Monday"),
) -> Path:
    """Save a compact mirrored-probability and points plot for one matchup."""
    plt.rcParams["font.family"] = "Segoe UI"
    data = matchup_df.copy()
    data["time"] = pd.to_datetime(data["time"])
    data = data.sort_values("time")
    teams = list(data["team"].drop_duplicates())[:2]
    if len(teams) != 2:
        raise ValueError("matchup_df must contain exactly two teams")
    day_names = list(days)
    day_dates = {day: _date_for_day(data, day) for day in day_names}
    widths = [_day_width(data, day_dates[day]) for day in day_names]
    frames = [data[data["team"].eq(team)].set_index("time") for team in teams]
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
    for col, day in enumerate(day_names):
        date = day_dates[day]
        edge_ax, points_ax = axes[0, col], axes[1, col]
        edge_data = frames[0][frames[0].index.date == date]
        if not edge_data.empty:
            edge = (edge_data["WinChance"] - 0.5) * 100
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
        edge_ax.set_title("")
        edge_ax.set_ylim(-50, 50)
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
        day_data = data[data["time"].dt.date == date]
        if not day_data.empty:
            edge_ax.set_xlim(day_data["time"].min(), day_data["time"].max())
            points_ax.set_xlim(day_data["time"].min(), day_data["time"].max())
        edge_ax.grid(axis="x", color="#ededed", lw=0.5)
        points_ax.grid(axis="x", color="#ededed", lw=0.5)
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
    fig.text(
        0.5,
        0.055,
        "solid = realized  ·  dashed = projected",
        color="#555555",
        fontsize=9,
        ha="center",
        va="center",
    )
    axes[0, 0].set_ylabel("Edge", fontsize=AXIS_TITLE_SIZE, fontweight="bold")
    axes[1, 0].set_ylabel("Points", fontsize=AXIS_TITLE_SIZE, fontweight="bold")
    output = Path(savepath)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _date_for_day(data: pd.DataFrame, day: str):
    matches = data[data["time"].dt.day_name().eq(day)]
    return matches["time"].dt.date.iloc[0] if not matches.empty else None


def _day_width(data: pd.DataFrame, date) -> float:
    if date is None:
        return 1.0
    day = data[data["time"].dt.date == date]
    return (
        max((day["time"].max() - day["time"].min()).total_seconds(), 1.0)
        if not day.empty
        else 1.0
    )


def _format_date(date) -> str:
    return f"{date.month}/{date.day}" if date is not None else ""
