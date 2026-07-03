"""
Generic RSS feed fetcher.

Handles multiple RSS feeds defined in sources.yaml.
Each feed is parsed with feedparser and normalized to RawArticle.
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
from src.curator.models import ContentType, RawArticle, SourcePriority

logger = logging.getLogger(__name__)

# Mapping from config content_type strings to ContentType enum
CONTENT_TYPE_MAP: dict[str, ContentType] = {
    "industry": ContentType.INDUSTRY,
    "research": ContentType.RESEARCH,
    "dev_tool": ContentType.DEV_TOOL,
}


class RSSFetcher(SourceProtocol):
    """Fetches articles from a single RSS feed."""

    def __init__(
        self,
        name: str,
        feed_url: str,
        content_type: ContentType,
        priority: SourcePriority = SourcePriority.CORE,
        language: str = "en",
        max_items: int = 20,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self._name = name
        self.feed_url = feed_url
        self._content_type = content_type
        self._priority = priority
        self.language = language
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return f"rss_{self._name.lower().replace(' ', '_')}"

    @property
    def default_content_type(self) -> ContentType:
        return self._content_type

    @property
    def priority(self) -> SourcePriority:
        return self._priority

    async def fetch(self) -> list[RawArticle]:
        """Fetch and parse the RSS feed."""
        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                response = await client.get(self.feed_url)
                response.raise_for_status()
                feed_data = response.text
        except Exception as e:
            logger.error(f"RSS fetch failed for {self._name}: {e}")
            return []

        try:
            feed = feedparser.parse(feed_data)
        except Exception as e:
            logger.error(f"RSS parse failed for {self._name}: {e}")
            return []

        if feed.bozo and not feed.entries:
            logger.warning(f"Malformed RSS feed '{self._name}': {feed.bozo_exception}")
            return []

        articles: list[RawArticle] = []
        for entry in feed.entries[: self.max_items]:
            try:
                # Extract published time
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                # Clean description (strip HTML tags)
                description = ""
                if hasattr(entry, "summary"):
                    from bs4 import BeautifulSoup
                    description = BeautifulSoup(entry.summary, "lxml").get_text(strip=True)
                elif hasattr(entry, "description"):
                    from bs4 import BeautifulSoup
                    description = BeautifulSoup(entry.description, "lxml").get_text(strip=True)

                articles.append(RawArticle(
                    title=entry.get("title", "").strip(),
                    url=canonicalize_url(entry.get("link", "")),
                    description=description[:500],
                    source=self.source_name,
                    content_type=self._content_type,
                    priority=self._priority,
                    published_at=published_at,
                    metadata={
                        "feed_name": self._name,
                        "language": self.language,
                    },
                ))
            except Exception as e:
                logger.debug(f"Skipping RSS entry from {self._name}: {e}")
                continue

        logger.info(f"RSS '{self._name}': fetched {len(articles)} articles")
        return articles


def create_rss_fetchers(config: dict) -> list[SourceProtocol]:
    """Create RSS fetchers from the sources configuration.

    Handles both the structured rss_feeds list and individual RSS source entries
    like techcrunch_ai.
    """
    fetchers: list[SourceProtocol] = []
    sources = config.get("sources", {})

    # Handle the rss_feeds list (量子位, 机器之心, etc.)
    rss_feeds = sources.get("rss_feeds", [])
    for feed_cfg in rss_feeds:
        if isinstance(feed_cfg, dict) and feed_cfg.get("enabled", True):
            ct_str = feed_cfg.get("content_type", "industry")
            priority_str = feed_cfg.get("priority", "core")
            try:
                priority = SourcePriority(priority_str)
            except ValueError:
                priority = SourcePriority.CORE

            fetchers.append(RSSFetcher(
                name=feed_cfg["name"],
                feed_url=feed_cfg["url"],
                content_type=CONTENT_TYPE_MAP.get(ct_str, ContentType.INDUSTRY),
                priority=priority,
                language=feed_cfg.get("language", "en"),
                max_items=feed_cfg.get("max_items", 20),
                timeout=config.get("global", {}).get("request_timeout", 30),
                user_agent=config.get("global", {}).get(
                    "user_agent", "AI-Info-Collector/1.0"
                ),
            ))

    # Handle individual RSS-like entries (techcrunch_ai)
    for src_name, src_cfg in sources.items():
        if not isinstance(src_cfg, dict):
            continue
        if not src_cfg.get("enabled", True):
            continue
        if "url" not in src_cfg:
            continue
        # Skip if it's a framework watch or other non-RSS source
        if src_cfg.get("repos") or src_cfg.get("topics") or src_cfg.get("tools"):
            continue
        if src_cfg.get("endpoint"):
            continue
        if src_cfg.get("since"):
            continue
        # Skip sources that are already handled by specialized fetchers
        if src_name in ("product_hunt", "hacker_news", "mcp_pulse",
                        "claude_plugins", "framework_watch", "coding_tools",
                        "oss_models", "official_blogs", "github_trending",
                        "huggingface_papers"):
            continue
        if src_name == "rss_feeds" or src_name == "global":
            continue

        ct_str = src_cfg.get("content_type", "industry")
        priority_str = src_cfg.get("priority", "core")
        try:
            priority = SourcePriority(priority_str)
        except ValueError:
            priority = SourcePriority.CORE

        auxiliary = src_cfg.get("priority") == "auxiliary"

        fetchers.append(RSSFetcher(
            name=src_name,
            feed_url=src_cfg["url"],
            content_type=CONTENT_TYPE_MAP.get(ct_str, ContentType.INDUSTRY),
            priority=priority,
            language=src_cfg.get("language", "en"),
            max_items=src_cfg.get("max_items", 15),
            timeout=config.get("global", {}).get("request_timeout", 30),
            user_agent=config.get("global", {}).get(
                "user_agent", "AI-Info-Collector/1.0"
            ),
        ))

        # Mark auxiliary sources
        if auxiliary:
            for fetcher in fetchers:
                pass  # already set via priority

    return fetchers
