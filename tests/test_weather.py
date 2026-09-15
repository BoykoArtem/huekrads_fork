from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_weather_content_helpers_and_stub_callback_contract(fake_context):
    from handlers import weather

    moscow_alias = weather.MOSCOW_ALIASES[0]
    assert weather._geo_query_name(moscow_alias) == weather.CITY_GEO_QUERY[moscow_alias]
    assert weather._bonus_photo(moscow_alias) in weather.MOSCOW_PHOTO_IDS
    result_id = "abcdefghijklmnopQRST"
    markup = weather._stub_keyboard(result_id)
    assert markup.inline_keyboard[0][0].callback_data == "wxabcdefghijklmnop"
    weather._store_attach(fake_context, result_id, "photo", "file-id", "caption")
    assert weather._peek_attach(fake_context, result_id) == ("photo", "file-id", "caption")
    assert weather._pop_attach(fake_context, None, result_id[:16]) == ("photo", "file-id", "caption")


@pytest.mark.asyncio
async def test_empty_inline_weather_query_does_not_call_network(fake_context, monkeypatch):
    from handlers import weather

    inline_query = SimpleNamespace(query="", answer=AsyncMock())
    monkeypatch.setattr(weather, "_fetch_weather_html", lambda _city: (_ for _ in ()).throw(AssertionError("network")))
    await weather.weather_inline_query(SimpleNamespace(inline_query=inline_query), fake_context)
    inline_query.answer.assert_awaited_once_with([], cache_time=1, is_personal=True)


def test_weather_fetch_uses_mocked_http(monkeypatch):
    from handlers import weather

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    api_name = weather.CITY_GEO_QUERY[weather.MOSCOW_ALIASES[0]]
    responses = iter([
        Response({"results": [{"latitude": 55.75, "longitude": 37.61, "name": api_name}]}),
        Response({"current_weather": {"weathercode": 0, "temperature": 20, "windspeed": 3}}),
    ])
    monkeypatch.setattr(weather.requests, "get", lambda *args, **kwargs: next(responses))
    text, city = weather._fetch_weather_html(weather.MOSCOW_ALIASES[0])
    assert city == api_name
    assert "20" in text
