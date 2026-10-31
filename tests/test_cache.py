import json

import httpx

from rates_forecasting.data.cache import Cache


def test_secret_is_not_written_and_cache_is_resumable(tmp_path, monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"observations": []})

    monkeypatch.setattr(httpx, "get", get)
    c = Cache(tmp_path)
    c.get("https://example.invalid/synthetic", {"api_key": "SYNTHETIC_SECRET", "series_id": "TEST"})
    cached = Cache(tmp_path, offline=True).get(
        "https://example.invalid/synthetic", {"api_key": "different", "series_id": "TEST"}
    )
    assert len(calls) == 1 and cached.json() == {"observations": []}
    for p in tmp_path.iterdir():
        assert b"SYNTHETIC_SECRET" not in p.read_bytes()
    meta = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert "api_key" not in meta["params"]
