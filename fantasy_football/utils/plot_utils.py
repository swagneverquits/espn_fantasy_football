import logging

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.dates import DateFormatter


def set_plot_style():
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.family"] = ["Noto Sans", "Noto Emoji"]
    sns.set_palette("colorblind")
    pd.set_option("display.max_columns", 100)


def plot_matchup(matchup_df, team1, team2, days, width_ratios, savepath, week):
    fig, axs = plt.subplots(
        2,
        len(days),
        figsize=(12, 6),
        sharey="row",
        sharex="col",
        gridspec_kw={
            "width_ratios": width_ratios[: len(days)],
            "height_ratios": [3, 2],
        },
    )

    # handle case when len(days) == 1 (axs not 2D)
    if len(days) == 1:
        axs = np.array(axs).reshape(2, 1)

    for j, day in enumerate(days):
        matchup_day_df = matchup_df.loc[str(day)]
        show_legend = j == (len(days) - 1)

        # --- WinChance ---
        ax = axs[0, j]
        matchup_day_df["WinChance"].plot.area(
            ax=ax,
            color=["goldenrod", "purple"],
            lw=0,
            alpha=0.9,
            legend=False,
        )
        matchup_day_df["WinChance"][team1].plot.line(ax=ax, c="yellow", label="_")
        if show_legend:
            ax.legend(frameon=True)

        ax.axhline(0.5, ls="--", c="k")
        ax.grid(True, c="k")

        ax.set_title(day.strftime("%A %Y-%m-%d"))
        ax.set_ylabel("Win Probability", weight="bold")
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=1))
        ax.set_xlim(matchup_day_df.index.min(), matchup_day_df.index.max())
        ax.xaxis.set_major_formatter(DateFormatter("%I:%M %p"))

        # --- Score & Projection ---
        ax = axs[1, j]
        matchup_day_df["Projected"].plot(
            ax=ax, color=["goldenrod", "purple"], ls="--", alpha=0.5, legend=False
        )
        matchup_day_df["Score"].plot(ax=ax, color=["goldenrod", "purple"], legend=False)
        ax.set_ylabel("Score", weight="bold")
        ax.set_xlabel("Time", weight="bold")

    plt.suptitle(
        f"Week {week}\n{team1} vs. {team2}",
        fontsize="x-large",
        weight="bold",
    )
    fig.tight_layout()
    fig.subplots_adjust(wspace=0.05)
    fig.savefig(savepath)
    plt.close(fig)
    logging.info(f"Saved plot → {savepath}")
