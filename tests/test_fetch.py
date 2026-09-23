"""Offline checks for the fetch client's rules: no network, no token needed."""
import os, time
os.environ.setdefault("BGG_TOKEN", "test-token")

import httpx
from src import fetch
from src.fetch import BGGClient, batched, _batch_filename


def test_batching_respects_20_id_limit():
    assert [len(b) for b in batched(range(45))] == [20, 20, 5]


def test_auth_header_and_host(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"<items/>")

    client = BGGClient(delay=0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler),
                                  headers=client._client.headers)
    assert client.get("thing", {"id": "1"}) == b"<items/>"
    assert seen["auth"] == "Bearer test-token"
    assert seen["url"].startswith("https://boardgamegeek.com/xmlapi2/thing")
    assert "www.boardgamegeek.com" not in seen["url"]


def test_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"<items/>")

    client = BGGClient(delay=0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.get("thing", {"id": "1"}) == b"<items/>"
    assert calls["n"] == 3
    assert client.stats.retries == 2


def test_202_is_retried_not_failed(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(202) if calls["n"] == 1 else httpx.Response(200, content=b"<x/>")

    client = BGGClient(delay=0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.get("thing", {"id": "1"}) == b"<x/>"
    assert client.stats.failures == 0


def test_throttle_waits_between_requests(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    client = BGGClient(delay=5.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<x/>"))
    )
    client.get("thing", {"id": "1"})
    client.get("thing", {"id": "2"})
    assert slept and slept[-1] > 4.5, f"expected a ~5s wait, got {slept}"


def test_resumable_skips_cached_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "THING_DIR", tmp_path)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"<items/>")

    def make_client():
        c = BGGClient(delay=0)
        c._client = httpx.Client(transport=httpx.MockTransport(handler))
        return c

    ids = list(range(1, 25))
    with make_client() as c:
        fetch.fetch_things(ids, client=c)
    first_round = len(requested)
    assert first_round == 2  # 24 ids -> 2 batches

    with make_client() as c:
        stats = fetch.fetch_things(ids, client=c)
    assert len(requested) == first_round, "cached ids were re-fetched"
    assert stats.cached_skipped == 24


def test_batch_filename_is_order_independent():
    assert _batch_filename([3, 1, 2]) == _batch_filename([1, 2, 3])
