"""
Abstract base classes for data source aggregators.

Defines the SourceProtocol interface that every aggregator must implement,
along with shared utilities for URL normalization and HTTP sessions.
"""

import hashlib
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

import httpx

from src.curator.models import ContentType, RawArticle, SourcePriority


class SourceProtocol(ABC):
    """Interface that every data source aggregator must implement."""

    @abstractmethod
    async def fetch(self) -> list[RawArticle]:
        """
        Fetch articles from the source.

        Returns:
            List of RawArticle objects. Returns empty list on failure
            (never raises — graceful degradation).
        """
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source (e.g. 'github_trending')."""
        ...

    @property
    @abstractmethod
    def default_content_type(self) -> ContentType:
        """Default content type for articles from this source."""
        ...

    @property
    def priority(self) -> SourcePriority:
        """Priority tier for this source."""
        return SourcePriority.CORE

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.source_name})"


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def canonicalize_url(url: str) -> str:
    """
    Canonicalize a URL for deduplication.

    - Lowercase scheme and host
    - Remove default ports (80, 443)
    - Remove fragment
    - Remove common tracking params (utm_*, ref, source)
    - Remove trailing slash
    - Unescape safe characters
    """
    if not url:
        return url

    parsed = urlparse(url.strip())

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Remove fragment
    # Rebuild without fragment

    # Remove tracking params from query string
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
    }
    query_params = parsed.query
    if query_params:
        pairs = query_params.split("&")
        filtered = []
        for p in pairs:
            if "=" not in p:
                filtered.append(p)
                continue
            key = p.split("=", 1)[0].lower()
            if key not in tracking_params:
                filtered.append(p)
        query_params = "&".join(filtered) if filtered else ""

    # Remove trailing slash from path
    path = parsed.path
    if path.endswith("/") and path != "/":
        path = path[:-1]

    canonical = urlunparse((scheme, netloc, path, parsed.params, query_params, ""))
    return unquote(canonical)


def url_hash(url: str) -> str:
    """Generate a short hash for a URL (used as a key in seen_urls)."""
    return hashlib.md5(canonicalize_url(url).encode()).hexdigest()[:12]


def create_http_client(
    timeout: int = 30, user_agent: str = "AI-Info-Collector/1.0"
) -> httpx.AsyncClient:
    """Create a configured httpx async client."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        headers={"User-Agent": user_agent},
        follow_redirects=True,
    )


class RateLimiter:
    """Simple token-bucket rate limiter for API calls."""

    def __init__(self, delay_ms: int = 500):
        self.delay = delay_ms / 1000.0
        self._last_call: float = 0.0

    async def wait(self) -> None:
        """Wait if needed to respect rate limit."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.delay:
            await __import__("asyncio").sleep(self.delay - elapsed)
        self._last_call = time.monotonic()
