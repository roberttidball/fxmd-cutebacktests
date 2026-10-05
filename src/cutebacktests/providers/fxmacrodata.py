from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests


class FXMacroDataProvider:
    """Fetch macroeconomic release calendars from FXMacroData."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fxmacrodata.com/v1",
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        if self.api_key and any(ch.isspace() for ch in self.api_key):
            raise ValueError("FXMacroData api_key must not contain whitespace")
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
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        url = f"{self.base_url}/calendar/{currency.lower()}"
        # Redirects are not followed so the key header is never replayed to another host.
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.is_redirect:
            raise RuntimeError(f"FXMacroData returned an unexpected redirect (HTTP {response.status_code}) for {url}")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"FXMacroData returned a non-JSON response for {url}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise RuntimeError(f"FXMacroData returned an unexpected response for {url}" + (f": {detail}" if detail else ""))
        rows = [row for row in data if isinstance(row, dict)]
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

