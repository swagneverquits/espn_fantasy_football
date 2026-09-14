"""Phone-oriented PNGs with chronological time running downward."""

import math
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.offsetbox import (
    AnchoredOffsetbox,
    AnnotationBbox,
    HPacker,
    TextArea,
    VPacker,
)
from matplotlib.patches import FancyBboxPatch
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator, NullFormatter

from fantasy_football.constants import (
    DEFAULT_SEASON,
    SEASON_COL,
    TEAM_ID_COL,
    TIMESTAMP_COL,
)

from .constants import (
    PROJECTED_COL,
    SCORE_COL,
    TEAM_COL,
    TEAM_COLORS,
    TEAM_FILL_COLORS,
    TEAM_FONT,
    ENDPOINT_VALUE_FONT,
    ENDPOINT_VALUE_FONTSIZE,
    WIN_CHANCE_COL,
)
from .timeline import compressed_timeline, game_windows
from .swings import probability_swings


def _asymmetric_probability_scale(
    probabilities: pd.Series,
    *,
    plot_width_pixels: float,
) -> tuple[float, float, tuple[float, ...], tuple[str, ...], tuple[float, ...]]:
    """Return independent extents plus adaptive labels and 5-point grid ticks."""
    valid = pd.to_numeric(probabilities, errors="coerce")
    valid = valid[valid.between(0, 1)]
    display_edge = 50 - valid * 100
    left_required = max(float(-display_edge.min()), 0.0) if not valid.empty else 0.0
    right_required = max(float(display_edge.max()), 0.0) if not valid.empty else 0.0
    buffer = 2.5
    left_extent = max(
        2.5, math.ceil(round((left_required + buffer) / 2.5, 10)) * 2.5
    )
    right_extent = max(
        2.5, math.ceil(round((right_required + buffer) / 2.5, 10)) * 2.5
    )
    left_extent = min(left_extent, 50.0)
    right_extent = min(right_extent, 50.0)
    pixels_per_point = plot_width_pixels / (left_extent + right_extent)
    label_interval = next(
        (
            interval
            for interval in (5.0, 10.0, 20.0, 25.0)
            if pixels_per_point * interval >= 60
        ),
        25.0,
    )
    negative_ticks = list(
        -value
        for value in np.arange(label_interval, left_extent + 0.001, label_interval)
    )
    positive_ticks = list(
        value
        for value in np.arange(label_interval, right_extent + 0.001, label_interval)
    )
    if np.isclose(left_extent, 50.0):
        negative_ticks.append(-50.0)
    if np.isclose(right_extent, 50.0):
        positive_ticks.append(50.0)
    ticks = tuple(sorted(set(negative_ticks + [0.0] + positive_ticks)))
    labels = tuple("EVEN" if tick == 0 else f"{50 + abs(tick):g}%" for tick in ticks)
    grid_ticks = tuple(
        sorted(
            {
                *np.arange(-5.0, -left_extent - 0.001, -5.0),
                0.0,
                *np.arange(5.0, right_extent + 0.001, 5.0),
            }
        )
    )
    even_fraction = left_extent / (left_extent + right_extent)
    if left_extent != right_extent:
        assert even_fraction != 0.5
    return left_extent, right_extent, ticks, labels, grid_ticks


def _crop_unused_bottom(fig, *, dpi: int, padding_pixels: int = 40) -> None:
    """Crop unused bottom canvas while preserving the rendered plot geometry."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    text_boxes = [
        text.get_window_extent(renderer)
        for text in fig.findobj(Text)
        if text.get_visible() and text.get_text()
    ]
    if not text_boxes:
        return

    old_height_pixels = fig.get_figheight() * dpi
    content_bottom = min(box.y0 for box in text_boxes)
    new_height_pixels = old_height_pixels - max(content_bottom - padding_pixels, 0)
    if new_height_pixels >= old_height_pixels:
        return

    old_height = fig.get_figheight()
    new_height = new_height_pixels / dpi
    for axis in fig.axes:
        position = axis.get_position()
        top_distance = (1 - position.y1) * old_height
        bottom_distance = (1 - position.y0) * old_height
        new_y1 = 1 - top_distance / new_height
        new_y0 = 1 - bottom_distance / new_height
        axis.set_position([position.x0, new_y0, position.width, new_y1 - new_y0])
    for text in fig.texts:
        x, y = text.get_position()
        text.set_position((x, 1 - (1 - y) * old_height / new_height))
    for artist in fig.artists:
        if isinstance(artist, FancyBboxPatch):
            artist.set_bounds(0.015, 0.012, 0.97, 0.976)
        elif isinstance(artist, AnchoredOffsetbox) and hasattr(
            artist, "_portrait_anchor_y"
        ):
            anchor_y = artist._portrait_anchor_y
            artist.set_bbox_to_anchor(
                (0.5, 1 - (1 - anchor_y) * old_height / new_height),
                transform=fig.transFigure,
            )
    fig.set_size_inches(fig.get_figwidth(), new_height)


def _plot_colored_probability_path(ax, edge, time_values) -> None:
    """Draw the probability path in team color, splitting crossings at Even."""
    edge = np.asarray(edge, dtype=float)
    time_values = np.asarray(time_values, dtype=float)
    segments = []
    colors = []
    for x0, x1, y0, y1 in zip(edge[:-1], edge[1:], time_values[:-1], time_values[1:]):
        if x0 * x1 < 0:
            crossing_y = y0 + (y1 - y0) * (-x0 / (x1 - x0))
            segments.extend(
                (
                    [(x0, y0), (0, crossing_y)],
                    [(0, crossing_y), (x1, y1)],
                )
            )
            colors.extend(
                (
                    TEAM_COLORS[0] if x0 < 0 else TEAM_COLORS[1],
                    TEAM_COLORS[0] if x1 < 0 else TEAM_COLORS[1],
                )
            )
            continue
        color = TEAM_COLORS[0] if (x0 < 0 or x1 < 0) else TEAM_COLORS[1]
        if x0 == 0 and x1 == 0:
            color = "#666666"
        elif x0 == 0 or x1 == 0:
            color = TEAM_COLORS[0] if (x0 + x1) < 0 else TEAM_COLORS[1]
        segments.append([(x0, y0), (x1, y1)])
        colors.append(color)
    if segments:
        ax.add_collection(
            LineCollection(
                segments,
                colors=colors,
                linewidths=1.8,
                zorder=2.5,
            )
        )


def _team_record(frame: pd.DataFrame) -> str:
    """Format an optional season record from the joined team metadata."""
    required = ("wins", "losses", "ties")
    if not all(column in frame for column in required):
        return ""
    row = frame[list(required)].dropna().iloc[-1:] if not frame.empty else frame
    if row.empty:
        return ""
    wins, losses, ties = (int(float(value)) for value in row.iloc[0])
    return f" ({wins}-{losses}-{ties})" if ties else f" ({wins}-{losses})"


def plot_matchup(
    matchup_df: pd.DataFrame,
    *,
    league_name: str,
    week: int | str,
    matchup: int | str,
    savepath: str | Path,
    window_gap_seconds: int = 1800,
    season: int | None = None,
    tag_swings: float | None = None,
) -> Path:
    """Render a phone-oriented 1000x1500 matchup PNG."""
    data = matchup_df.copy()
    times = data[TIMESTAMP_COL]
    data[TIMESTAMP_COL] = pd.to_datetime(
        times, unit="s" if pd.api.types.is_numeric_dtype(times) else None, utc=True
    ).dt.tz_convert("America/New_York")
    data = data.sort_values(TIMESTAMP_COL)
    ids = data[TEAM_ID_COL].drop_duplicates().tolist()
    if len(ids) != 2:
        raise ValueError("matchup_df must contain exactly two teams")
    if season is None:
        seasons = data[SEASON_COL].dropna().unique() if SEASON_COL in data else []
        if len(seasons) > 1:
            raise ValueError("A matchup plot must contain only one season")
        season = int(seasons[0]) if len(seasons) else DEFAULT_SEASON
    windows = game_windows(data, window_gap_seconds)
    active = pd.Series(False, index=data.index)
    for window_start, window_end in windows:
        active |= data[TIMESTAMP_COL].between(window_start, window_end)
    data = data.loc[active].copy()
    frames = [data[data[TEAM_ID_COL].eq(team)] for team in ids]
    start, end = data[TIMESTAMP_COL].min(), data[TIMESTAMP_COL].max()
    timeline, map_time, timeline_end = compressed_timeline(windows)
    lower, upper = 0.0, timeline_end
    durations = [
        mdates.date2num(end) - mdates.date2num(start) for start, end in windows
    ]
    current_gap = max(max(durations, default=1 / 24) * 0.12, 0.15 / 24)
    current_timeline_end = sum(durations) + current_gap * max(len(durations) - 1, 0)
    figure_height = 10 * timeline_end / current_timeline_end * 1.32

    with plt.rc_context({"font.family": "Segoe UI"}):
        fig = plt.figure(
            figsize=(1000 / 135, figure_height), dpi=135, facecolor="#f5f5f5"
        )
        fig.add_artist(
            FancyBboxPatch(
                (0.015, 0.012),
                0.97,
                0.976,
                transform=fig.transFigure,
                boxstyle="round,pad=0,rounding_size=0.02",
                facecolor="white",
                edgecolor="none",
                zorder=-1,
            )
        )
        fig.text(
            0.5,
            0.97,
            f"{league_name} \u00b7 {season} Week {week}",
            fontsize=20,
            fontweight="bold",
            va="top",
            ha="center",
        )
        team_a, team_b = [
            f"{frame[TEAM_COL].iloc[-1]}{_team_record(frame)}" for frame in frames
        ]
        matchup_line = HPacker(
            children=[
                TextArea(
                    team_a,
                    textprops={
                        "color": TEAM_COLORS[0],
                        "fontproperties": TEAM_FONT,
                        "fontsize": 14,
                    },
                ),
                TextArea(
                    "vs.",
                    textprops={
                        "color": "#666666",
                        "fontsize": 11,
                        "fontweight": "normal",
                    },
                ),
                TextArea(
                    team_b,
                    textprops={
                        "color": TEAM_COLORS[1],
                        "fontproperties": TEAM_FONT,
                        "fontsize": 14,
                    },
                ),
            ],
            align="center",
            pad=0,
            sep=8,
        )
        matchup_artist = AnchoredOffsetbox(
            loc="center",
            child=matchup_line,
            pad=0,
            borderpad=0,
            frameon=False,
            bbox_to_anchor=(0.5, 0.935),
            bbox_transform=fig.transFigure,
        )
        matchup_artist._portrait_anchor_y = 0.935
        fig.add_artist(matchup_artist)
        axes = fig.subplots(1, 2, sharey=True, gridspec_kw={"width_ratios": [1.1, 1]})
        fig.subplots_adjust(left=0.13, right=0.94, bottom=0.13, top=0.86, wspace=0.22)
        probability_ax, points_ax = axes
        probability_position = probability_ax.get_position()
        points_position = points_ax.get_position()
        panel_gap = points_position.x0 - probability_position.x1
        probability_ax.set_position(
            [
                0.06,
                probability_position.y0,
                points_position.x0 - panel_gap - 0.095,
                probability_position.height,
            ]
        )
        visualization_left = probability_ax.get_position().x0
        visualization_right = points_ax.get_position().x1
        fig.add_artist(
            Line2D(
                [visualization_left, visualization_right],
                [0.905, 0.905],
                transform=fig.transFigure,
                color="#C4C4C4",
                linewidth=1.0,
                solid_capstyle="butt",
                zorder=2,
            )
        )
        fig.text(
            probability_ax.get_position().x0 + probability_ax.get_position().width / 2,
            0.885,
            "Win Probability",
            fontsize=13,
            fontweight="medium",
            color="#4A4A4A",
            ha="center",
        )
        fig.text(
            points_ax.get_position().x0 + points_ax.get_position().width / 2,
            0.885,
            "Points",
            fontsize=13,
            fontweight="medium",
            color="#4A4A4A",
            ha="center",
        )
        time_axis_x = (
            probability_ax.get_position().x1 + points_ax.get_position().x0
        ) / 2
        (
            left_extent,
            right_extent,
            ticks,
            labels,
            grid_ticks,
        ) = _asymmetric_probability_scale(
            frames[0][WIN_CHANCE_COL],
            plot_width_pixels=probability_ax.get_window_extent().width,
        )

        # Both charts use identical elapsed-time coordinates, including overnight gaps.
        hour_locator = mdates.HourLocator(interval=1, tz="America/New_York")
        grid_hours = []
        label_hours = []
        label_texts = []
        label_window_indices = []
        for window_index, (raw_start, raw_end, _, _) in enumerate(timeline):
            raw_hours = hour_locator.tick_values(
                mdates.num2date(raw_start, tz="America/New_York"),
                mdates.num2date(raw_end, tz="America/New_York"),
            )
            raw_hours = raw_hours[(raw_hours >= raw_start) & (raw_hours <= raw_end)]
            grid_hours.extend(map_time(raw_hours))
            labeled_raw_hours = raw_hours[::3]
            label_hours.extend(map_time(labeled_raw_hours))
            label_texts.extend(
                mdates.num2date(value, tz="America/New_York")
                .strftime("%I %p")
                .lstrip("0")
                for value in labeled_raw_hours
            )
            label_window_indices.extend([window_index] * len(labeled_raw_hours))
        # Keep the top tick labels close to the first gridline while preserving
        # the shared timeline geometry in both panels.
        top_timeline_margin = timeline_end * 0.005
        for ax in (probability_ax, points_ax):
            ax.set_ylim(upper + top_timeline_margin, lower - timeline_end * 0.01)
            ax.spines[:].set_visible(False)
            ax.yaxis.set_major_locator(FixedLocator(label_hours))
            ax.yaxis.set_minor_locator(FixedLocator(grid_hours))
            ax.yaxis.set_major_formatter(NullFormatter())
            ax.yaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(axis="both", which="both", length=0, labelsize=12, pad=6)
            ax.tick_params(axis="y", labelleft=False, labelright=False)
            ax.set_axisbelow(True)
            ax.tick_params(
                axis="x",
                labeltop=True,
                labelbottom=False,
                pad=-6,
            )
        probability_ax.set_xlim(-left_extent, right_extent)
        probability_ax.set_xticks(ticks, labels)
        even_label = next(
            label
            for label in probability_ax.get_xticklabels()
            if label.get_text() == "EVEN"
        )
        even_label.set_fontweight("medium")
        even_label.set_color("#555555")
        minor_ticks = tuple(value for value in grid_ticks if value not in ticks)
        probability_ax.set_xticks(minor_ticks, minor=True)
        # Rotate the existing paths; do not join observations across collection outages.
        for first, last in windows:
            probability = frames[0][frames[0][TIMESTAMP_COL].between(first, last)]
            time_values = map_time(mdates.date2num(probability[TIMESTAMP_COL]))
            edge = 50 - probability[WIN_CHANCE_COL] * 100
            probability_ax.fill_betweenx(
                time_values,
                0,
                edge,
                where=edge <= 0,
                color=TEAM_FILL_COLORS[0],
                alpha=0.54,
            )
            probability_ax.fill_betweenx(
                time_values,
                0,
                edge,
                where=edge > 0,
                color=TEAM_FILL_COLORS[1],
                alpha=0.54,
            )
            _plot_colored_probability_path(probability_ax, edge, time_values)
            for frame, color in zip(frames, TEAM_COLORS):
                selected = frame[frame[TIMESTAMP_COL].between(first, last)]
                points_ax.plot(
                    selected[SCORE_COL],
                    map_time(mdates.date2num(selected[TIMESTAMP_COL])),
                    color=color,
                    lw=2,
                    zorder=3,
                    clip_on=False,
                )

        if tag_swings is not None:
            swings = probability_swings(frames[0], minimum_pp=tag_swings)
            for swing in swings:
                edge = 50 - swing.after * 100
                point_time = map_time([mdates.date2num(swing.timestamp)])[0]
                sign = "+" if swing.delta_pp > 0 else ""
                probability_ax.annotate(
                    f"Δ {sign}{swing.delta_pp:.0f} pp",
                    (edge, point_time),
                    xytext=(10 if edge >= 0 else -10, -10),
                    textcoords="offset points",
                    ha="left" if edge >= 0 else "right",
                    va="top",
                    color="#4A4A4A",
                    fontsize=10,
                    fontweight="medium",
                    annotation_clip=False,
                    zorder=5,
                )
        actual = pd.to_numeric(data[SCORE_COL], errors="coerce")
        actual = actual[np.isfinite(actual)]
        points_ax.set_xlim(0, max(1, float(actual.max()) * 1.22) if len(actual) else 1)
        # Draw both grid directions only inside active windows; the compressed
        # interval between segments remains completely blank in both panels.
        for ax in (probability_ax, points_ax):
            for raw_start, raw_end, mapped_start, mapped_end in timeline:
                window_hours = hour_locator.tick_values(
                    mdates.num2date(raw_start, tz="America/New_York"),
                    mdates.num2date(raw_end, tz="America/New_York"),
                )
                window_hours = window_hours[
                    (window_hours >= raw_start) & (window_hours <= raw_end)
                ]
                for y in map_time(window_hours):
                    ax.hlines(
                        y,
                        *ax.get_xlim(),
                        color="#dddddd",
                        lw=0.5,
                        zorder=0.5,
                    )
                x_grid = ax.get_xticks()
                if ax is probability_ax:
                    x_grid = np.concatenate((x_grid, ax.get_xticks(minor=True)))
                for x in x_grid:
                    ax.vlines(
                        x,
                        mapped_start,
                        mapped_end,
                        color="#dddddd",
                        lw=0.5,
                        zorder=0.5,
                    )
                if ax is probability_ax:
                    ax.vlines(
                        0,
                        mapped_start,
                        mapped_end,
                        color="#b0b0b0",
                        lw=0.85,
                        zorder=0.8,
                    )
                    for boundary in (
                        -50.0 if np.isclose(left_extent, 50.0) else None,
                        50.0 if np.isclose(right_extent, 50.0) else None,
                    ):
                        if boundary is not None:
                            ax.vlines(
                                boundary,
                                mapped_start,
                                mapped_end,
                                color="#999999",
                                lw=0.7,
                                zorder=0.75,
                            )

        # Render one shared clock/date axis in the gutter between the plots.
        def figure_y(display_time):
            display_point = probability_ax.transData.transform((0, display_time))
            return fig.transFigure.inverted().transform(display_point)[1]

        clock_artists = []
        for display_time, label, window_index in zip(
            label_hours, label_texts, label_window_indices
        ):
            clock_artists.append(
                (
                    window_index,
                    fig.text(
                        time_axis_x,
                        figure_y(display_time),
                        label,
                        fontsize=12,
                        ha="center",
                        va="center",
                        color="#222222",
                    ),
                )
            )
        date_artists = []
        for window_index, (raw_start, _, mapped_start, mapped_end) in enumerate(
            timeline
        ):
            day = mdates.num2date(raw_start, tz="America/New_York")
            date_position = mapped_start + min(
                (mapped_end - mapped_start) * 0.12, 0.2 / 24
            )
            date_artists.append(
                (
                    window_index,
                    fig.text(
                        time_axis_x,
                        figure_y(date_position),
                        f"{day.strftime('%a').upper()} · {day.month}/{day.day}",
                        fontsize=12,
                        fontweight="medium",
                        color="#555555",
                        ha="center",
                        va="center",
                    ),
                )
            )

        # Date headers own the window start; suppress only colliding clock text.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        safety_pixels = 6
        for window_index, date_artist in date_artists:
            date_box = date_artist.get_window_extent(renderer)
            date_box = (
                date_box.x0,
                date_box.y0 - safety_pixels,
                date_box.x1,
                date_box.y1 + safety_pixels,
            )
            for clock_window_index, clock_artist in clock_artists:
                if clock_window_index != window_index:
                    continue
                clock_box = clock_artist.get_window_extent(renderer)
                if (
                    clock_box.x0 < date_box[2]
                    and clock_box.x1 > date_box[0]
                    and clock_box.y0 < date_box[3]
                    and clock_box.y1 > date_box[1]
                ):
                    clock_artist.remove()
        valid = frames[0][frames[0][WIN_CHANCE_COL].between(0, 1)]
        if not valid.empty:
            row = valid.iloc[-1]
            edge = 50 - float(row[WIN_CHANCE_COL]) * 100
            point_time = map_time([mdates.date2num(row[TIMESTAMP_COL])])[0]
            color = (
                TEAM_COLORS[0]
                if edge < 0
                else TEAM_COLORS[1] if edge > 0 else "#222222"
            )
            probability_ax.plot(
                edge,
                point_time,
                "o",
                color="#222222",
                markersize=5,
                markeredgecolor="white",
                zorder=5,
            )
            probability_ax.annotate(
                f"{50 + abs(edge):.0f}%",
                (edge, point_time),
                xytext=(
                    8
                    if edge <= -50
                    else -8
                    if edge >= 50
                    else -8
                    if edge < 0
                    else 8,
                    0,
                ),
                textcoords="offset points",
                ha=(
                    "left"
                    if edge <= -50
                    else "right"
                    if edge >= 50
                    else "right"
                    if edge < 0
                    else "left"
                ),
                va="center",
                color=color,
                fontproperties=ENDPOINT_VALUE_FONT,
                fontsize=ENDPOINT_VALUE_FONTSIZE,
                annotation_clip=False,
            )
        # Latest actual points stay primary; projections are secondary below them.
        endpoint_specs = []
        for frame, color in zip(frames, TEAM_COLORS):
            valid = frame[frame[SCORE_COL].notna()]
            if valid.empty:
                continue
            row = valid.iloc[-1]
            score = float(row[SCORE_COL])
            point_time = map_time([mdates.date2num(row[TIMESTAMP_COL])])[0]
            points_ax.plot(
                score,
                point_time,
                "o",
                color=color,
                markersize=5,
                markeredgecolor="white",
                clip_on=False,
                zorder=5,
            )
            projected = row[PROJECTED_COL]
            endpoint_specs.append(
                (
                    score,
                    point_time,
                    color,
                    f"{score:.1f}",
                    f"Proj {projected:.1f}" if pd.notna(projected) else "Proj --",
                )
            )

        def add_endpoint_label(spec, place_right):
            score, point_time, color, score_text, projection_text = spec
            annotation_lines = VPacker(
                children=[
                    TextArea(
                        score_text,
                        textprops={
                            "color": color,
                            "fontproperties": ENDPOINT_VALUE_FONT,
                            "fontsize": ENDPOINT_VALUE_FONTSIZE,
                        },
                    ),
                    TextArea(
                        projection_text,
                        textprops={
                            "color": color,
                            "fontsize": 11.5,
                            "alpha": 0.95,
                        },
                    ),
                ],
                align="left" if place_right else "right",
                sep=-1,
                pad=0,
            )
            artist = AnnotationBbox(
                annotation_lines,
                (score, point_time),
                xybox=(8 if place_right else -8, 0),
                xycoords="data",
                boxcoords="offset points",
                box_alignment=(0, 0.5) if place_right else (1, 0.5),
                frameon=False,
                pad=0,
                annotation_clip=False,
                zorder=6,
            )
            points_ax.add_artist(artist)
            return artist

        # Both labels start on the right. If they collide, put the lower score
        # on the left and the higher score on the right; ties use team order.
        labels = [add_endpoint_label(spec, True) for spec in endpoint_specs]
        if len(labels) == 2:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            if (
                labels[0]
                .get_window_extent(renderer)
                .overlaps(labels[1].get_window_extent(renderer))
            ):
                first_score = endpoint_specs[0][0]
                second_score = endpoint_specs[1][0]
                if first_score <= second_score:
                    left_index, right_index = 0, 1
                else:
                    left_index, right_index = 1, 0
                labels[0].remove()
                labels[1].remove()
                labels = [None, None]
                labels[left_index] = add_endpoint_label(
                    endpoint_specs[left_index], False
                )
                labels[right_index] = add_endpoint_label(
                    endpoint_specs[right_index], True
                )

        # Keep right-side labels inside the card as an edge-case fallback.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        card_right = fig.bbox.x1 - 2
        for index, artist in enumerate(labels):
            if artist.get_window_extent(renderer).x1 > card_right:
                artist.remove()
                labels[index] = add_endpoint_label(endpoint_specs[index], False)
        final_left, final_right = probability_ax.get_xlim()
        final_even_fraction = (0 - final_left) / (final_right - final_left)
        assert np.isclose(final_left, -left_extent)
        assert np.isclose(final_right, right_extent)
        if left_extent != right_extent:
            assert not np.isclose(final_even_fraction, 0.5)
        output = Path(savepath)
        output.parent.mkdir(parents=True, exist_ok=True)
        _crop_unused_bottom(fig, dpi=135)
        fig.savefig(output, dpi=135)
        plt.close(fig)
    return output
