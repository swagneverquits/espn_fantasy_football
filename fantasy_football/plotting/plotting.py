"""Prepare and generate compact matchup plots from Parquet snapshots."""

import math
import textwrap
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from fantasy_football.constants import (
    DEFAULT_SEASON,
    MATCHUP_ID_COL,
    SEASON_COL,
    TEAM_ID_COL,
    TIMESTAMP_COL,
)
from fantasy_football.plotting.constants import (
    AXIS_TITLE_SIZE,
    DATE_SIZE,
    EDGE_LIMIT,
    EDGE_LIMIT_STEP,
    EDGE_MIN_LIMIT,
    EDGE_PADDING,
    HOUR_SIZE,
    LEAGUE_NAME_COL,
    MAIN_TITLE_SIZE,
    PROJECTED_COL,
    SCORE_COL,
    TEAM_COL,
    TEAM_COLORS,
    TEAM_FILL_COLORS,
    TEAM_FONT,
    TEAM_LABEL_SIZE,
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
    window_gap_seconds: int = 30 * 60,
    full_edge_scale: bool = False,
    season: int | None = None,
) -> Path:
    """Save a compact mirrored-probability and points plot for one matchup."""
    # Normalize the input and identify the two teams and game-day windows.
    plt.rcParams["font.family"] = "Segoe UI"
    data = matchup_df.copy()
    if season is None:
        seasons = data[SEASON_COL].dropna().unique() if SEASON_COL in data else []
        if len(seasons) > 1:
            raise ValueError("A matchup plot must contain only one season")
        season = int(seasons[0]) if len(seasons) else DEFAULT_SEASON
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
    windows = _game_windows(data, window_gap_seconds)
    widths = [max((end - start).total_seconds(), 60) for start, end in windows]
    frames = [
        data[data[TEAM_ID_COL].eq(team_id)].set_index(TIMESTAMP_COL)
        for team_id in team_ids
    ]
    edge_limit, edge_ticks, edge_labels = _edge_scale(
        frames[0][WIN_CHANCE_COL], full_edge_scale
    )
    latest_probability = frames[0][WIN_CHANCE_COL].dropna()
    latest_probability = latest_probability[latest_probability.between(0, 1)]
    # Create aligned Edge and Points panels for each game day.
    fig, axes = plt.subplots(
        2,
        len(windows),
        figsize=(10, 5),
        sharey="row",
        sharex="col",
        squeeze=False,
        gridspec_kw={"height_ratios": [1.4, 1], "width_ratios": widths},
    )
    fig.subplots_adjust(
        left=0.04, right=0.94, top=0.86, bottom=0.11, wspace=0.014, hspace=0.24
    )
    fig.suptitle(
        f"{league_name} \u00b7 {season} Week {week} \u00b7 Matchup {matchup}",
        fontsize=MAIN_TITLE_SIZE,
        fontweight="bold",
        x=0.04,
        y=0.97,
        ha="left",
    )
    # Render each day independently so discontinuities remain visible.
    for col, (start, end) in enumerate(windows):
        edge_ax, points_ax = axes[0, col], axes[1, col]
        edge_data = frames[0][(frames[0].index >= start) & (frames[0].index <= end)]
        if not edge_data.empty:
            edge = (edge_data[WIN_CHANCE_COL] - 0.5) * 100
            x = edge_data.index
            edge_ax.fill_between(
                x, 0, edge, where=edge >= 0, color=TEAM_FILL_COLORS[0], alpha=0.54
            )
            edge_ax.fill_between(
                x, 0, edge, where=edge < 0, color=TEAM_FILL_COLORS[1], alpha=0.54
            )
            edge_ax.plot(x, edge, color="#222222", lw=1.8)
        for frame, color in zip(frames, TEAM_COLORS):
            day_data = frame[(frame.index >= start) & (frame.index <= end)]
            if not day_data.empty:
                points_ax.plot(
                    day_data.index,
                    day_data[SCORE_COL],
                    color=color,
                    lw=2.0,
                    zorder=3,
                    clip_on=False,
                )
        # Apply shared scales, grids, spines, and date-axis formatting.
        edge_ax.set_title("")
        edge_ax.set_ylim(-edge_limit, edge_limit)
        edge_ax.set_yticks(edge_ticks, labels=edge_labels)
        edge_ax.grid(axis="y", visible=False)
        edge_ax.spines[:].set_visible(False)
        edge_ax.set_axisbelow(True)
        edge_ax.tick_params(axis="y", labelsize=TICK_SIZE)
        points_ax.grid(axis="y", visible=False)
        points_ax.spines[:].set_visible(False)
        points_ax.set_axisbelow(True)
        points_ax.tick_params(axis="y", labelsize=TICK_SIZE)
        if col:
            edge_ax.tick_params(axis="y", left=False, labelleft=False)
            points_ax.tick_params(axis="y", left=False, labelleft=False)
        # Anchor labels to the first visible hourly gridline in this game window.
        hourly = mdates.HourLocator(interval=1, tz="America/New_York")
        hours = hourly.tick_values(start.to_pydatetime(), end.to_pydatetime())
        hours = hours[
            (hours >= mdates.date2num(start)) & (hours <= mdates.date2num(end))
        ]
        points_ax.xaxis.set_major_locator(FixedLocator(hours[::3]))
        points_ax.xaxis.set_major_formatter(
            FuncFormatter(
                lambda value, _: mdates.num2date(value, tz="America/New_York")
                .strftime("%I %p")
                .lstrip("0")
            )
        )
        points_ax.xaxis.set_minor_locator(
            mdates.HourLocator(interval=1, tz="America/New_York")
        )
        points_ax.xaxis.set_minor_formatter(NullFormatter())
        points_ax.tick_params(axis="x", which="both", length=0, bottom=False, top=False)
        edge_ax.tick_params(
            axis="x", which="both", length=0, bottom=False, top=False, labelbottom=False
        )
        points_ax.tick_params(axis="x", labelsize=HOUR_SIZE, pad=2)
        points_ax.set_xlabel(
            f"{start.day_name()[:3]}. {start.month}/{start.day}",
            fontsize=DATE_SIZE,
            fontweight="medium",
            labelpad=3,
        )
        day_data = data[data[TIMESTAMP_COL].between(start, end)]
        if not day_data.empty:
            edge_ax.set_xlim(
                day_data[TIMESTAMP_COL].min(), day_data[TIMESTAMP_COL].max()
            )
            points_ax.set_xlim(
                day_data[TIMESTAMP_COL].min(), day_data[TIMESTAMP_COL].max()
            )
        # Shared x-axis locators align the temporal ruler exactly across both rows.
        for ax in (edge_ax, points_ax):
            ax.grid(axis="x", which="both", color="#e8e8e8", lw=0.5, alpha=1)
    # Scale all Points panels from actual scores only, across every game window.
    actual = pd.to_numeric(data[SCORE_COL], errors="coerce")
    actual = actual[actual.map(math.isfinite)]
    maximum = float(actual.max()) if not actual.empty else 0
    minimum = float(actual.min()) if not actual.empty else 0
    axes[1, 0].set_ylim(min(0, minimum * 1.1), max(1, maximum * 1.2))
    # Unclipped tick-aligned gridlines retain their full stroke at plot boundaries.
    for row, row_axes in enumerate(axes):
        for ax in row_axes:
            lower, upper = ax.get_ylim()
            for tick in ax.get_yticks():
                if lower <= tick <= upper:
                    even = row == 0 and tick == 0
                    ax.axhline(
                        tick,
                        color="#b0b0b0" if even else "#eeeeee",
                        lw=0.75 if even else 0.5,
                        zorder=1.8 if even else 0.5,
                        clip_on=False,
                        gid="horizontal-reference" if even else "horizontal-grid",
                    )
    # Mark the latest actual scores and anchor the totals to those endpoints.
    endpoints = []
    for frame, color in zip(frames, TEAM_COLORS):
        valid = frame[
            pd.to_numeric(frame[SCORE_COL], errors="coerce").map(
                lambda value: pd.notna(value) and math.isfinite(value)
            )
        ]
        if valid.empty:
            continue
        latest = valid.iloc[-1]
        timestamp = valid.index[-1]
        col = next(
            i for i, (start, end) in enumerate(windows) if start <= timestamp <= end
        )
        endpoints.append(
            (
                axes[1, col],
                timestamp,
                float(latest[SCORE_COL]),
                latest[PROJECTED_COL],
                color,
            )
        )
    offsets = [0.0] * len(endpoints)
    if len(endpoints) == 2 and endpoints[0][0] is endpoints[1][0]:
        ax = endpoints[0][0]
        low, high = ax.get_ylim()
        separation = (
            abs(endpoints[0][2] - endpoints[1][2])
            / (high - low)
            * ax.bbox.height
            * 72
            / fig.dpi
        )
        if separation < 30:
            shift = (30 - separation) / 2
            offsets = (
                [shift, -shift]
                if endpoints[0][2] >= endpoints[1][2]
                else [-shift, shift]
            )
    label_center = (fig.subplotpars.right + 1) / 2
    for (ax, timestamp, score, projected, color), offset in zip(endpoints, offsets):
        ax.plot(
            timestamp,
            score,
            marker="o",
            markersize=5,
            color=color,
            markeredgecolor="white",
            markeredgewidth=0.8,
            clip_on=False,
            zorder=5,
        )
        projection = f"{projected:.1f}" if pd.notna(projected) else "--"
        ax.annotate(
            f"{score:.1f}",
            xy=(timestamp, score),
            xytext=(label_center, offset),
            textcoords=("figure fraction", "offset points"),
            ha="center",
            va="center",
            fontsize=TICK_SIZE,
            fontweight="bold",
            color=color,
            annotation_clip=False,
            arrowprops=(
                {"arrowstyle": "-", "color": color, "lw": 0.6} if offset else None
            ),
            zorder=6,
        )
        ax.annotate(
            f"Proj {projection}",
            xy=(timestamp, score),
            xytext=(label_center, offset - 10),
            textcoords=("figure fraction", "offset points"),
            ha="center",
            va="center",
            fontsize=TICK_SIZE - 1,
            fontweight="normal",
            color=color,
            alpha=0.85,
            annotation_clip=False,
            zorder=6,
        )
    # Keep the latest probability in the white gutter, outside the data panels.
    if not latest_probability.empty:
        latest_edge = (float(latest_probability.iloc[-1]) - 0.5) * 100
        latest_time = latest_probability.index[-1]
        latest_col = next(
            i for i, (start, end) in enumerate(windows) if start <= latest_time <= end
        )
        axes[0, latest_col].plot(
            latest_time,
            latest_edge,
            marker="o",
            markersize=5,
            color="#222222",
            markeredgecolor="white",
            markeredgewidth=0.8,
            clip_on=False,
            zorder=5,
        )
        axes[0, -1].annotate(
            f"{50 + abs(latest_edge):.0f}%",
            xy=(1, latest_edge),
            xycoords=("axes fraction", "data"),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=TICK_SIZE,
            fontweight="bold",
            color=(
                TEAM_COLORS[0]
                if latest_edge > 0
                else TEAM_COLORS[1] if latest_edge < 0 else "#222222"
            ),
            annotation_clip=False,
            zorder=5,
        )
    # Add matchup-level team direction labels.
    fig.text(
        0.5,
        axes[0, 0].get_position().y0 + axes[0, 0].get_position().height * 0.875,
        textwrap.fill(teams[0], 28),
        color=TEAM_COLORS[0],
        fontsize=TEAM_LABEL_SIZE,
        fontproperties=TEAM_FONT,
        va="center",
        ha="center",
        linespacing=1.05,
    )
    # Add matchup-level team direction labels.
    fig.text(
        0.5,
        axes[0, 0].get_position().y0 + axes[0, 0].get_position().height * 0.125,
        textwrap.fill(teams[1], 28),
        color=TEAM_COLORS[1],
        fontsize=TEAM_LABEL_SIZE,
        fontproperties=TEAM_FONT,
        va="center",
        ha="center",
        linespacing=1.05,
    )
    # Add matchup-level team direction labels.
    # Label the shared y-axes and save the finished figure.
    axes[0, 0].set_title(
        "Win probability",
        loc="left",
        fontsize=AXIS_TITLE_SIZE,
        fontweight="bold",
        pad=8,
    )
    axes[1, 0].set_title(
        "Points", loc="left", fontsize=AXIS_TITLE_SIZE, fontweight="bold", pad=8
    )
    output = Path(savepath)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _edge_scale(
    probabilities: pd.Series, full_scale: bool = False
) -> tuple[float, tuple[float, ...], tuple[str, ...]]:
    """Choose one padded symmetric range for the entire matchup, in percentage points."""
    valid = pd.to_numeric(probabilities, errors="coerce")
    valid = valid[valid.between(0, 1)]
    limit = float(EDGE_LIMIT)
    if not full_scale and not valid.empty:
        peak = float(((valid - 0.5) * 100).abs().max())
        limit = min(
            EDGE_LIMIT,
            max(
                EDGE_MIN_LIMIT,
                math.ceil(peak * EDGE_PADDING / EDGE_LIMIT_STEP) * EDGE_LIMIT_STEP,
            ),
        )
    ticks = (-limit, -limit / 2, 0, limit / 2, limit)
    labels = tuple("Even" if tick == 0 else f"{50 + abs(tick):g}%" for tick in ticks)
    return limit, ticks, labels


def _game_windows(
    data: pd.DataFrame, gap_seconds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Infer independent collection windows from gaps, including midnight crossings."""
    if gap_seconds <= 0:
        raise ValueError("window_gap_seconds must be positive")
    times = data[TIMESTAMP_COL].drop_duplicates().sort_values()
    groups = times.diff().dt.total_seconds().gt(gap_seconds).cumsum()
    return [(group.iloc[0], group.iloc[-1]) for _, group in times.groupby(groups)]


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
    window_gap_seconds: int = 30 * 60,
    full_edge_scale: bool = False,
    season: int | None = None,
    portrait: bool = False,
) -> list[Path]:
    """Render every matchup from already loaded data; no configuration or queries."""
    if data.empty:
        return []
    data = normalize_team_names(data)
    if data[LEAGUE_NAME_COL].notna().any():
        league_name = data[LEAGUE_NAME_COL].dropna().iloc[-1]
    paths = []
    renderer = plot_matchup
    if portrait:
        from .portrait import plot_matchup_portrait

        renderer = plot_matchup_portrait
    for number, (matchup_id, matchup) in enumerate(
        data.groupby(MATCHUP_ID_COL, sort=True), start=1
    ):
        paths.append(
            renderer(
                matchup,
                league_name=league_name,
                week=week,
                matchup=matchup_id,
                window_gap_seconds=window_gap_seconds,
                full_edge_scale=full_edge_scale,
                season=season,
                savepath=Path(output_dir)
                / f"matchup{number}{'_portrait' if portrait else ''}.png",
            )
        )
    return paths
