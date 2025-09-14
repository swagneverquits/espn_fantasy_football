import pandas as pd


def normalize_team_names(matchup_df: pd.DataFrame) -> pd.DataFrame:
    """Sometimes, teams can change their names mid-matchup. This addresses that... sort of"""
    # Ensure sorted by time
    matchup_df = matchup_df.sort_index()

    # For each matchup, normalize names by slot position
    updated = []
    for matchup, df_m in matchup_df.groupby("Matchup", group_keys=False):
        # reset index temporarily to preserve row order per timestamp
        df_m = df_m.reset_index()

        # Create a slot ID: 0 or 1 depending on order within each timestamp
        df_m["slot"] = df_m.groupby("time").cumcount()

        # Find the most recent team name for each slot
        most_recent = (
            df_m.groupby("slot")
                .tail(1)
                .set_index("slot")["team"]
                .to_dict()
        )

        # Replace all names in df_m with the most recent name per slot
        df_m["team"] = df_m["slot"].map(most_recent)

        updated.append(df_m.set_index(["time", "team"]))

    # Recombine matchups
    return pd.concat(updated).sort_index()
