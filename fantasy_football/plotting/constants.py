"""Shared configuration for matchup analysis and plots."""

from matplotlib.font_manager import FontProperties, fontManager

# Foregrounds use a slightly darker amber; probability fills retain their color.
TEAM_COLORS = ("#b88600", "#5b2a86")
TEAM_FILL_COLORS = ("#d49a00", "#5b2a86")
_AVAILABLE_FONTS = {font.name for font in fontManager.ttflist}
_HAS_SEMIBOLD = any(
    font.name == "Segoe UI" and font.weight == 600 and font.style == "normal"
    for font in fontManager.ttflist
)
TEAM_FONT = FontProperties(
    family=[
        name
        for name in (
            "Segoe UI",
            "Segoe UI Emoji",
            "Noto Sans",
            "Noto Emoji",
            "DejaVu Sans",
        )
        if name in _AVAILABLE_FONTS
    ],
    weight="semibold" if _HAS_SEMIBOLD else "bold",
)

# Figure typography
DEFAULT_GAME_DAYS = ("Thursday", "Sunday", "Monday")
MAIN_TITLE_SIZE = 17
AXIS_TITLE_SIZE = 12.5
DATE_SIZE = 10.5
TICK_SIZE = 9.5
TEAM_LABEL_SIZE = 10
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
EDGE_MIN_LIMIT = 10
EDGE_PADDING = 1.15
EDGE_LIMIT_STEP = 5
