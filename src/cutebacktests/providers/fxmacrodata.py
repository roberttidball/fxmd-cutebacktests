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
        if self.api_key and any(
            ch.isspace() or not ch.isprintable() for ch in self.api_key
        ):
            raise ValueError(
                "FXMacroData api_key must not contain whitespace or control characters"
            )
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
        try:
            response = self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.RequestException:
            raise RuntimeError("FXMacroData request failed") from None
        if response.is_redirect:
            raise RuntimeError(
                f"FXMacroData returned an unexpected redirect (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError("FXMacroData returned a non-JSON response") from None
        data = payload.get("data") if isinstance(payload, dict) else None
        if (
            not isinstance(data, list)
            or not all(isinstance(row, dict) for row in data)
            or payload.get("error")
            or payload.get("detail")
        ):
            raise RuntimeError("FXMacroData returned an unexpected response")
        rows = data
        if top_tier_only:
            rows = [
                row
                for row in rows
                if row.get("top_tier_for_currency") is True
                or (type(row.get("market_tier")) is int and row["market_tier"] == 1)
            ]
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
        return [
            row
            for row in rows
            if (event_time := _event_time(row)) is not None and now <= event_time <= end
        ]


def _event_time(row: Dict[str, Any]) -> Optional[datetime]:
    utc_value = row.get("announcement_datetime_utc")
    text = utc_value or row.get("announcement_datetime_local")
    if not isinstance(text, str) or "T" not in text:
        return None
    try:
        event_time = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if event_time.tzinfo is None:
        if not utc_value:
            return None
        event_time = event_time.replace(tzinfo=timezone.utc)
    return event_time.astimezone(timezone.utc)
