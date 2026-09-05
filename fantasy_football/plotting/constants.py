"""Shared configuration for matchup analysis and plots."""

from pathlib import Path

from matplotlib.font_manager import FontProperties

# Team and font styling
TEAM_COLORS = ("#d49a00", "#5b2a86")
_EMOJI_FONT_PATHS = (
    Path(r"C:\Windows\Fonts\seguiemj.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
)
_EMOJI_FONT_PATH = next((path for path in _EMOJI_FONT_PATHS if path.exists()), None)
EMOJI_FONT = (
    FontProperties(fname=str(_EMOJI_FONT_PATH))
    if _EMOJI_FONT_PATH
    else FontProperties(family="DejaVu Sans")
)

# Figure typography
DEFAULT_GAME_DAYS = ("Thursday", "Sunday", "Monday")
MAIN_TITLE_SIZE = 17
AXIS_TITLE_SIZE = 12.5
DATE_SIZE = 11.5
TICK_SIZE = 9.5
HOUR_SIZE = 9
ANNOTATION_SIZE = 9

# Normalized plotting columns
TEAM_COL = "team_name"
SCORE_COL = "score_live"
PROJECTED_COL = "projected_live"
WIN_CHANCE_COL = "win_probability"
LEAGUE_NAME_COL = "league_name"
# Edge-axis scale
EDGE_LIMIT = 50
EDGE_TICKS = (-50, -25, 0, 25, 50)
EDGE_TICK_LABELS = ("100%", "75%", "Even", "75%", "100%")
