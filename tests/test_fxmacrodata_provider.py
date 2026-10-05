from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

import requests

from cutebacktests.providers.fxmacrodata import FXMacroDataProvider


def _response(status: int, body: object = None, headers: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = b"" if body is None else json.dumps(body).encode()
    response.url = "https://api.fxmacrodata.com/v1/calendar/usd"
    return response


def _provider(response: requests.Response, api_key: str = "test-key") -> tuple[FXMacroDataProvider, MagicMock]:
    session = MagicMock()
    session.get.return_value = response
    return FXMacroDataProvider(api_key=api_key, session=session), session


class FXMacroDataProviderTests(unittest.TestCase):
    def test_returns_rows_and_sends_key_header(self) -> None:
        provider, session = _provider(_response(200, {"data": [{"release": "cpi", "market_tier": 1}]}))

        rows = provider.fetch_calendar("USD")

        self.assertEqual(rows, [{"release": "cpi", "market_tier": 1}])
        kwargs = session.get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-key")
        self.assertIs(kwargs["allow_redirects"], False)

    def test_redirect_raises_instead_of_forwarding_key(self) -> None:
        provider, session = _provider(_response(302, headers={"Location": "https://other.example/calendar"}))

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


if __name__ == "__main__":
    unittest.main()
