from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests


class FXMacroDataProvider:
    """Fetch macroeconomic release calendars from FXMacroData."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://fxmacrodata.com/api/v1",
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def fetch_calendar(
        self,
        currency: str = "usd",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        top_tier_only: bool = False,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        response = self._session.get(
            f"{self.base_url}/calendar/{currency.lower()}",
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = list((response.json() or {}).get("data") or [])
        if top_tier_only:
            rows = [row for row in rows if row.get("top_tier_for_currency") or row.get("market_tier") == 1]
        return rows

    def upcoming_events(
        self,
        currency: str = "usd",
        now: Optional[datetime] = None,
        lookahead: timedelta = timedelta(days=7),
        top_tier_only: bool = True,
    ) -> List[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        end = now + lookahead
        rows = self.fetch_calendar(
            currency=currency,
            start_date=now.date().isoformat(),
            end_date=end.date().isoformat(),
            top_tier_only=top_tier_only,
        )
        return [row for row in rows if (event_time := _event_time(row)) is not None and now <= event_time <= end]


def _event_time(row: Dict[str, Any]) -> Optional[datetime]:
    text = str(row.get("announcement_datetime_utc") or row.get("announcement_datetime_local") or "")
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))

