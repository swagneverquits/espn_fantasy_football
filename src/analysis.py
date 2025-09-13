import pandas as pd
import numpy as np
import logging

# ------------------------
# Config & Style
# ------------------------
from src.config import RESULTS_DIR, PLOTS_DIR
from src.utils.io_utils import get_results_file, get_plots_dir
from src.utils.plot_utils import plot_matchup, set_plot_style

set_plot_style()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SEASON = 2025
WEEK = 1
LEAGUE_ID = 1012938436

results_file = get_results_file(SEASON, WEEK, LEAGUE_ID)
plots_path = get_plots_dir(SEASON, WEEK, LEAGUE_ID)

# ------------------------
# Load & Prep Data
# ------------------------
df = pd.read_csv(results_file)
df["time"] = pd.to_datetime(df["time"])
df["date"] = df["time"].dt.date
df = df.set_index(["time", "team"])

num_matchups = int(df["Matchup"].max()) + 1

# Precompute day lengths for subplot width ratios
lengths = (
    df.reset_index()
    .groupby("date")["time"]
    .agg(["min", "max"])
    .assign(diff=lambda x: (x["max"] - x["min"]).dt.total_seconds())
)
width_ratios = lengths["diff"].astype(float).values

# ------------------------
# Main Loop
# ------------------------
for i in range(num_matchups):
    matchup_df = df[df["Matchup"].eq(i)]
    days = np.unique(matchup_df["date"])

    matchup_df = pd.pivot_table(
        matchup_df,
        index="time",
        columns="team",
        values=["Score", "Projected", "WinChance"],
    )

    team1, team2 = matchup_df["WinChance"].columns
    savepath = plots_path / f"matchup{i}.png"
    plot_matchup(matchup_df, team1, team2, days, width_ratios, savepath, WEEK)
