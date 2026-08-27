"""Small client for ESPN's Fantasy Football league JSON endpoint."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_HOST = "https://lm-api-reads.fantasy.espn.com"
DEFAULT_VIEWS = (
    "mMatchup",
    "mMatchupScore",
    "mRoster",
    "mScoreboard",
    "mSettings",
    "mStatus",
    "mTeam",
)


class ESPNAPIError(RuntimeError):
    """Raised when ESPN returns an unusable API response."""


def build_league_url(season: int, league_id: int, views=DEFAULT_VIEWS) -> str:
    path = f"/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
    return f"{API_HOST}{path}?{urlencode([('view', view) for view in views])}"


def fetch_league_data(
    season: int, league_id: int, *, timeout: int = 30, espn_s2=None, swid=None
) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (Fantasy Football collector)"}
    cookies = []
    if espn_s2:
        cookies.append(f"espn_s2={espn_s2}")
    if swid:
        cookies.append(f"SWID={swid}")
    if cookies:
        headers["Cookie"] = "; ".join(cookies)

    try:
        with urlopen(
            Request(build_league_url(season, league_id), headers=headers),
            timeout=timeout,
        ) as response:
            data = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ESPNAPIError(
                "ESPN rejected the league request; set ESPN_S2 and ESPN_SWID for a private league"
            ) from exc
        raise ESPNAPIError(f"ESPN API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ESPNAPIError(f"Could not reach ESPN API: {exc.reason}") from exc
    except ValueError as exc:
        raise ESPNAPIError("ESPN API returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise ESPNAPIError("ESPN API returned an unexpected response shape")
    if data.get("messages"):
        raise ESPNAPIError("ESPN API error: " + "; ".join(map(str, data["messages"])))
    return data


def configured_cookies():
    return os.getenv("ESPN_S2"), os.getenv("ESPN_SWID") or os.getenv("SWID")
