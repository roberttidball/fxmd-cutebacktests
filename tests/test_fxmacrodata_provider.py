from __future__ import annotations

import json
import unittest
import traceback
from datetime import datetime, timezone
from unittest.mock import MagicMock

import requests

from cutebacktests.providers.fxmacrodata import FXMacroDataProvider, _event_time


def _response(
    status: int, body: object = None, headers: dict | None = None
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = b"" if body is None else json.dumps(body).encode()
    response.url = "https://api.fxmacrodata.com/v1/calendar/usd"
    return response


def _provider(
    response: requests.Response, api_key: str = "test-key"
) -> tuple[FXMacroDataProvider, MagicMock]:
    session = MagicMock()
    session.get.return_value = response
    return FXMacroDataProvider(api_key=api_key, session=session), session


class FXMacroDataProviderTests(unittest.TestCase):
    def test_returns_rows_and_sends_key_header(self) -> None:
        provider, session = _provider(
            _response(200, {"data": [{"release": "cpi", "market_tier": 1}]})
        )

        rows = provider.fetch_calendar("USD")

        self.assertEqual(rows, [{"release": "cpi", "market_tier": 1}])
        kwargs = session.get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-key")
        self.assertIs(kwargs["allow_redirects"], False)

    def test_redirect_raises_instead_of_forwarding_key(self) -> None:
        provider, session = _provider(
            _response(302, headers={"Location": "https://other.example/calendar"})
        )

        with self.assertRaises(RuntimeError) as ctx:
            provider.fetch_calendar("usd")

        self.assertIn("redirect", str(ctx.exception))
        self.assertEqual(session.get.call_count, 1)

    def test_key_with_whitespace_is_rejected_without_echo(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            FXMacroDataProvider(api_key="test key")
        self.assertNotIn("test key", str(ctx.exception))
        self.assertEqual(FXMacroDataProvider(api_key=" test-key\n").api_key, "test-key")

    def test_error_body_or_wrong_shape_raises_clean_error(self) -> None:
        for body in ({"detail": "Invalid API key"}, [], {"data": {"release": "cpi"}}):
            provider, _ = _provider(_response(200, body))
            with self.assertRaises(RuntimeError):
                provider.fetch_calendar("usd")

    def test_naive_utc_event_does_not_crash_upcoming_filter(self):
        provider, _ = _provider(
            _response(
                200,
                {
                    "data": [
                        {
                            "announcement_datetime_utc": "2026-10-20T12:30:00",
                            "market_tier": 1,
                        }
                    ]
                },
            )
        )
        self.assertEqual(
            len(
                provider.upcoming_events(
                    now=datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
                )
            ),
            1,
        )

    def test_local_offset_is_normalized_to_utc(self):
        self.assertEqual(
            _event_time({"announcement_datetime_local": "2026-10-20T08:30:00-04:00"}),
            datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc),
        )

    def test_naive_local_event_is_unavailable(self):
        self.assertIsNone(
            _event_time({"announcement_datetime_local": "2026-10-20T12:30:00"})
        )

    def test_malformed_event_is_unavailable(self):
        for value in ("invalid", "2026-10-20", 123):
            with self.subTest(value=value):
                self.assertIsNone(_event_time({"announcement_datetime_utc": value}))

    def test_reference_date_is_not_a_release_time(self):
        self.assertIsNone(_event_time({"date": "2026-10-20"}))

    def test_false_string_and_boolean_tier_are_not_top_tier(self):
        provider, _ = _provider(
            _response(
                200,
                {
                    "data": [
                        {"top_tier_for_currency": "false"},
                        {"market_tier": True},
                        {"top_tier_for_currency": True},
                    ]
                },
            )
        )
        self.assertEqual(
            provider.fetch_calendar(top_tier_only=True),
            [{"top_tier_for_currency": True}],
        )

    def test_error_envelope_with_data_is_rejected(self):
        provider, _ = _provider(_response(200, {"error": "failed", "data": []}))
        with self.assertRaises(RuntimeError):
            provider.fetch_calendar()

    def test_invalid_rows_are_not_silently_discarded(self):
        provider, _ = _provider(
            _response(200, {"data": [{"release": "cpi"}, "invalid"]})
        )
        with self.assertRaises(RuntimeError):
            provider.fetch_calendar()

    def test_error_details_are_sanitized(self):
        provider, _ = _provider(_response(200, {"detail": "sensitive upstream text"}))
        with self.assertRaises(RuntimeError) as caught:
            provider.fetch_calendar()
        self.assertNotIn("sensitive upstream text", str(caught.exception))

    def test_transport_traceback_is_sanitized(self):
        provider, session = _provider(_response(200, {"data": []}))
        session.get.side_effect = requests.ConnectionError("sensitive upstream text")
        try:
            provider.fetch_calendar()
        except RuntimeError as error:
            self.assertNotIn(
                "sensitive upstream text", "".join(traceback.format_exception(error))
            )
        else:
            self.fail("Expected transport error")

    def test_non_json_traceback_is_sanitized(self):
        provider, session = _provider(_response(200, {"data": []}))
        session.get.return_value.json = MagicMock(
            side_effect=ValueError("sensitive upstream text")
        )
        with self.assertRaises(RuntimeError) as caught:
            provider.fetch_calendar()
        self.assertTrue(caught.exception.__suppress_context__)

    def test_control_character_key_is_rejected(self):
        with self.assertRaises(ValueError):
            FXMacroDataProvider(api_key="test\x00key")


if __name__ == "__main__":
    unittest.main()
