"""Rate-limited, cached, resumable BGG XML API2 client.

Rules enforced here (see CLAUDE.md):
  * official XML API2 only, never HTML or private JSON endpoints
  * boardgamegeek.com, never www. (the redirect strips the auth header)
  * Bearer token on every request
  * <= 20 ids per thing call, >= 5s between requests
  * 500/503 -> exponential backoff, 202 -> wait and retry
  * every raw response hits disk before anything parses it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import httpx

from src.config import (
    API_BASE,
    BACKOFF_BASE,
    BATCH_SIZE,
    MAX_RETRIES,
    RAW_DIR,
    REQUEST_DELAY,
    RETRY_202_DELAY,
    bgg_token,
)

log = logging.getLogger(__name__)

THING_DIR = RAW_DIR / "thing"
COMMENTS_DIR = RAW_DIR / "ratingcomments"
INDEX_NAME = "index.jsonl"

RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class Stats:
    """Request counters, logged at the end of a run."""

    requests: int = 0
    retries: int = 0
    failures: int = 0
    cached_skipped: int = 0
    ids_fetched: int = 0
    failed_batches: list[list[int]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"requests={self.requests} retries={self.retries} failures={self.failures} "
            f"ids_fetched={self.ids_fetched} ids_already_cached={self.cached_skipped}"
        )


class BGGClient:
    """One client per run. Holds the HTTP session, the clock and the counters."""

    def __init__(self, delay: float = REQUEST_DELAY, timeout: float = 60.0):
        self.delay = delay
        self.stats = Stats()
        self._last_request = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {bgg_token()}",
                "Accept": "application/xml",
                "User-Agent": "bgg-crawler/0.1 (design-space research)",
            },
            follow_redirects=False,  # a redirect to www. would drop the auth header
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BGGClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, path: str, params: dict) -> bytes | None:
        """One API call with throttling and retries. None means give up."""
        url = f"{API_BASE}/{path}"
        backoff = BACKOFF_BASE

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self._client.get(url, params=params)
                self._last_request = time.monotonic()
                self.stats.requests += 1
            except httpx.HTTPError as exc:
                self._last_request = time.monotonic()
                self.stats.requests += 1
                self.stats.retries += 1
                log.warning("%s %s: transport error %s (attempt %d)", path, params, exc, attempt)
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 202:
                # Queued server-side. Wait and ask again; not an error.
                self.stats.retries += 1
                log.info("%s %s: 202 queued, retrying in %.0fs", path, params, RETRY_202_DELAY)
                time.sleep(RETRY_202_DELAY)
                continue
            if resp.status_code in RETRY_STATUS:
                self.stats.retries += 1
                log.warning(
                    "%s %s: HTTP %d, backing off %.0fs (attempt %d)",
                    path, params, resp.status_code, backoff, attempt,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code in (401, 403):
                raise RuntimeError(
                    f"HTTP {resp.status_code} from BGG - check BGG_TOKEN and that your "
                    "application is approved."
                )
            log.error("%s %s: HTTP %d, not retryable", path, params, resp.status_code)
            break

        self.stats.failures += 1
        return None


# --- cache index -------------------------------------------------------


def _index_path(directory: Path) -> Path:
    return directory / INDEX_NAME


def cached_ids(directory: Path = THING_DIR) -> set[int]:
    """Ids already on disk. Entries whose file vanished are ignored."""
    index = _index_path(directory)
    if not index.exists():
        return set()
    known: set[int] = set()
    with index.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if (directory / entry["file"]).exists():
                known.update(entry["ids"])
    return known


def _record(directory: Path, filename: str, ids: Sequence[int]) -> None:
    with _index_path(directory).open("a") as fh:
        fh.write(
            json.dumps({"file": filename, "ids": list(ids), "fetched_at": time.time()}) + "\n"
        )


def _batch_filename(ids: Sequence[int]) -> str:
    digest = hashlib.sha1(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()[:16]
    return f"thing_{digest}.xml"


def batched(ids: Iterable[int], size: int = BATCH_SIZE) -> Iterator[list[int]]:
    batch: list[int] = []
    for i in ids:
        batch.append(int(i))
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


# --- thing endpoint ----------------------------------------------------


def fetch_things(ids: Sequence[int], client: BGGClient | None = None) -> Stats:
    """Fetch `thing?stats=1` for every id not already cached.

    Resumable: re-running after an interrupt only fetches what is missing.
    """
    THING_DIR.mkdir(parents=True, exist_ok=True)
    owned_client = client is None
    client = client or BGGClient()

    try:
        have = cached_ids(THING_DIR)
        todo = [int(i) for i in dict.fromkeys(ids) if int(i) not in have]
        client.stats.cached_skipped += len(set(map(int, ids))) - len(todo)
        total = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
        log.info("thing: %d ids to fetch in %d batches (%d cached)", len(todo), total, len(have))

        for n, batch in enumerate(batched(todo), start=1):
            filename = _batch_filename(batch)
            path = THING_DIR / filename
            if path.exists():  # same batch shape seen before
                _record(THING_DIR, filename, batch)
                continue

            content = client.get(
                "thing",
                {"id": ",".join(map(str, batch)), "type": "boardgame", "stats": 1},
            )
            if content is None:
                client.stats.failed_batches.append(batch)
                log.error("batch %d/%d failed permanently: %s", n, total, batch)
                continue

            path.write_bytes(content)  # raw response on disk before any parsing
            _record(THING_DIR, filename, batch)
            client.stats.ids_fetched += len(batch)
            log.info("batch %d/%d ok (%d ids)", n, total, len(batch))

        log.info("fetch_things done: %s", client.stats.summary())
        if client.stats.failed_batches:
            log.warning(
                "%d batches failed; re-run to retry them", len(client.stats.failed_batches)
            )
        return client.stats
    finally:
        if owned_client:
            client.close()


# --- ratingcomments (finalists only) -----------------------------------


def fetch_rating_comments(
    game_id: int, max_pages: int = 50, client: BGGClient | None = None
) -> int:
    """Page through individual ratings for one game. Expensive: finalists only.

    100 ratings per page. Returns the number of pages saved.
    """
    out_dir = COMMENTS_DIR / str(game_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    owned_client = client is None
    client = client or BGGClient()

    try:
        saved = 0
        for page in range(1, max_pages + 1):
            path = out_dir / f"page_{page:03d}.xml"
            if path.exists():
                saved += 1
                continue

            content = client.get(
                "thing",
                {
                    "id": game_id,
                    "type": "boardgame",
                    "ratingcomments": 1,
                    "pagesize": 100,
                    "page": page,
                },
            )
            if content is None:
                log.error("game %d page %d failed", game_id, page)
                break

            path.write_bytes(content)
            saved += 1
            # A short page means we reached the end of the comment list.
            if content.count(b"<comment ") < 100:
                break
        log.info("game %d: %d comment pages cached", game_id, saved)
        return saved
    finally:
        if owned_client:
            client.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch BGG thing data for sampled ids.")
    ap.add_argument("--ids", help="comma-separated ids (default: read the sample table)")
    ap.add_argument("--limit", type=int, help="cap the number of ids, for smoke tests")
    ap.add_argument("--delay", type=float, default=REQUEST_DELAY)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.ids:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
    else:
        from src.db import connect

        with connect(read_only=True) as con:
            ids = [r[0] for r in con.execute("SELECT id FROM sample ORDER BY id").fetchall()]

    if args.limit:
        ids = ids[: args.limit]

    with BGGClient(delay=args.delay) as client:
        fetch_things(ids, client=client)


if __name__ == "__main__":
    main()
