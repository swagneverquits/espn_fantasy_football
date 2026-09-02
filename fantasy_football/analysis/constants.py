"""Shared configuration for matchup analysis and plots."""

from matplotlib.font_manager import FontProperties

# Team and font styling
TEAM_COLORS = ("#d49a00", "#5b2a86")
EMOJI_FONT = FontProperties(fname=r"C:\Windows\Fonts\seguiemj.ttf")

# Figure typography
DEFAULT_GAME_DAYS = ("Thursday", "Sunday", "Monday")
MAIN_TITLE_SIZE = 17
AXIS_TITLE_SIZE = 12.5
DATE_SIZE = 11.5
TICK_SIZE = 9.5
HOUR_SIZE = 9
ANNOTATION_SIZE = 9

# Normalized plotting columns
TIME_COL = "time"
TEAM_COL = "team"
MATCHUP_COL = "Matchup"
SCORE_COL = "Score"
PROJECTED_COL = "Projected"
WIN_CHANCE_COL = "WinChance"
LEAGUE_NAME_COL = "league_name"
# Edge-axis scale
EDGE_LIMIT = 50
EDGE_TICKS = (-50, -25, 0, 25, 50)
EDGE_TICK_LABELS = ("100%", "75%", "Even", "75%", "100%")
