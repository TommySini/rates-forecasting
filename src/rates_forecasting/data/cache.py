"""Small resumable HTTP cache. Secrets never enter cache keys, metadata or errors."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx


@dataclass
class Response:
    content: bytes
    metadata: dict

    @property
    def text(self):
        try:
            return self.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Early Fed announcements use Windows-1252, unlike the modern site.
            return self.content.decode("cp1252")

    def json(self):
        return json.loads(self.content)


class SourceUnavailable(RuntimeError):
    pass


class Cache:
    def __init__(self, root="data/raw", offline=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.offline = offline

    def get(self, url: str, params: dict | None = None) -> Response:
        params = params or {}
        if "api_key=" in url.lower():
            raise ValueError("Pass credentials only through params")
        public = {
            k: v
            for k, v in params.items()
            if k.lower() not in {"api_key", "token", "authorization"}
        }
        request = {"url": url, "params": public}
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        body_path = self.root / f"{digest}.body"
        meta_path = self.root / f"{digest}.json"
        if body_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            content = body_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != meta["sha256"]:
                raise ValueError(f"Corrupt raw cache entry: {digest}")
            return Response(content, meta)
        if self.offline:
            raise SourceUnavailable(f"Not cached: {url} {public}")
        for attempt in range(3):
            try:
                r = httpx.get(
                    url,
                    params=params,
                    timeout=45,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (RatesForecastingResearch/0.1)"},
                )
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                if r.status_code != 200:
                    raise SourceUnavailable(f"HTTP {r.status_code}: {url} {public}")
                meta = request | {
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "status_code": r.status_code,
                    "content_type": r.headers.get("content-type"),
                    "sha256": hashlib.sha256(r.content).hexdigest(),
                    "cache_id": digest,
                }
                for p, b in [
                    (body_path, r.content),
                    (meta_path, json.dumps(meta, indent=2).encode()),
                ]:
                    tmp = p.with_suffix(p.suffix + ".tmp")
                    tmp.write_bytes(b)
                    tmp.replace(p)
                return Response(r.content, meta)
            except httpx.HTTPError:
                # HTTP exception strings may contain the request URL and secret key.
                if attempt == 2:
                    raise SourceUnavailable(f"Network failure: {url} {public}") from None
        raise SourceUnavailable(f"Retries exhausted: {url} {public}")
