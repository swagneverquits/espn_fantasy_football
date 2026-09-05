"""Retrieve NFL kickoff times used by the live-polling schedule gate."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fantasy_football.constants import ESPN_SCHEDULE_URL


def _parse_start_time(value: Any) -> datetime:
    """Convert an ISO timestamp to UTC."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _schedule_rows(payload: Any) -> list[dict[str, Any]]:
    """Return event rows from the ESPN scoreboard response."""
    if not isinstance(payload, dict):
        raise ValueError("ESPN schedule response was not a JSON object")
    return [row for row in payload.get("events", []) if isinstance(row, dict)]


def fetch_nfl_game_starts(
    now: datetime | None = None,
    lookahead_days: int = 14,
    timeout: int = 30,
) -> list[datetime]:
    """Return upcoming and recently started NFL kickoffs in UTC."""
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lower = current_time - timedelta(hours=4)
    upper = current_time + timedelta(days=lookahead_days)
    query = urlencode({"limit": 1000, "dates": f"{lower:%Y%m%d}-{upper:%Y%m%d}"})
    request = Request(
        f"{ESPN_SCHEDULE_URL}?{query}",
        headers={
            "Accept": "application/json",
            "Referer": "https://www.espn.com/",
            "User-Agent": "Mozilla/5.0 (Fantasy Football collector)",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    starts = []
    for event in _schedule_rows(payload):
        start_value = event.get("date")
        if start_value is None:
            continue
        start = _parse_start_time(start_value)
        if lower <= start <= upper:
            starts.append(start)
    return sorted(starts)
