"""
Official AI company blog aggregator.

Monitors official blogs from Anthropic, OpenAI, and Google AI
for methodology guides, best practices, and product announcements.
"""

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)


class OfficialBlogsSource(SourceProtocol):
    """Aggregates official AI company blog posts."""

    def __init__(
        self,
        feeds: list[dict],
        max_items: int = 10,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.feeds = feeds  # [{name, url, content_type}, ...]
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "official_blogs"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.GUIDE

    def _map_content_type(self, ct_str: str) -> ContentType:
        """Map config content_type string to ContentType enum."""
        mapping = {
            "guide": ContentType.GUIDE,
            "industry": ContentType.INDUSTRY,
            "model_release": ContentType.MODEL_RELEASE,
            "research": ContentType.RESEARCH,
        }
        return mapping.get(ct_str, ContentType.GUIDE)

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed_cfg: dict
    ) -> list[RawArticle]:
        """Fetch and parse a single RSS feed."""
        articles: list[RawArticle] = []
        feed_name = feed_cfg.get("name", "Unknown")
        feed_url = feed_cfg.get("url", "")
        ct_str = feed_cfg.get("content_type", "guide")

        if not feed_url:
            return articles

        try:
            response = await client.get(feed_url)
            if response.status_code != 200:
                logger.debug(f"Official blog '{feed_name}' returned {response.status_code}")
                return articles

            feed = feedparser.parse(response.text)
        except Exception as e:
            logger.debug(f"Official blog '{feed_name}' fetch failed: {e}")
            return articles

        content_type = self._map_content_type(ct_str)

        for entry in feed.entries[: self.max_items]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            # Parse published date
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            # Get description
            description = ""
            if hasattr(entry, "summary"):
                from bs4 import BeautifulSoup
                description = BeautifulSoup(entry.summary, "lxml").get_text(strip=True)
            elif hasattr(entry, "description"):
                from bs4 import BeautifulSoup
                description = BeautifulSoup(entry.description, "lxml").get_text(strip=True)

            # Determine content type based on title heuristics
            final_content_type = content_type
            title_lower = title.lower()
            if any(kw in title_lower for kw in ["api", "model", "gpt", "claude", "gemini", "release"]):
                final_content_type = ContentType.MODEL_RELEASE
            elif any(kw in title_lower for kw in ["guide", "building", "how to", "best practice", "lesson", "pattern", "technique"]):
                final_content_type = ContentType.GUIDE

            articles.append(RawArticle(
                title=f"[{feed_name}] {title}",
                url=canonicalize_url(entry.get("link", "")),
                description=description[:500],
                source=self.source_name,
                content_type=final_content_type,
                published_at=published_at,
                metadata={
                    "blog_name": feed_name,
                    "feed_url": feed_url,
                },
            ))

        return articles

    async def fetch(self) -> list[RawArticle]:
        """Fetch all official blog feeds."""
        articles: list[RawArticle] = []

        async with create_http_client(self.timeout, self.user_agent) as client:
            for feed_cfg in self.feeds:
                if isinstance(feed_cfg, dict):
                    feed_articles = await self._fetch_feed(client, feed_cfg)
                    articles.extend(feed_articles)

        logger.info(f"Official Blogs: fetched {len(articles)} posts from {len(self.feeds)} feeds")
        return articles
