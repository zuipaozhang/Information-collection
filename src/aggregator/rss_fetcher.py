"""
Generic RSS feed fetcher + HTML scraping fallback.

Handles multiple feeds defined in sources.yaml.
Each feed is parsed with feedparser and normalized to RawArticle.
For feeds marked `scrape: true`, scrapes the HTML page for article links.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup

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
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                description = ""
                if hasattr(entry, "summary"):
                    description = BeautifulSoup(entry.summary, "lxml").get_text(strip=True)
                elif hasattr(entry, "description"):
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


class ScrapingFetcher(SourceProtocol):
    """Scrapes article links from an HTML page (fallback when RSS is unavailable)."""

    def __init__(
        self,
        name: str,
        page_url: str,
        content_type: ContentType,
        priority: SourcePriority = SourcePriority.CORE,
        language: str = "zh",
        max_items: int = 20,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self._name = name
        self.page_url = page_url
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
        """Scrape article links from the HTML page."""
        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                response = await client.get(self.page_url)
                response.raise_for_status()
                html = response.text
        except Exception as e:
            logger.error(f"Scrape failed for {self._name}: {e}")
            return []

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception as e:
            logger.error(f"HTML parse failed for {self._name}: {e}")
            return []

        articles: list[RawArticle] = []
        seen_urls: set[str] = set()

        # Try to find article links — common patterns for Chinese tech sites
        # Look for <a> tags that contain article titles (usually in h2/h3 or with specific classes)
        article_candidates = []

        # Pattern 1: Links inside article cards/list items
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Skip non-article links
            if not text or len(text) < 8:
                continue
            if any(skip in href.lower() for skip in ["login", "signup", "about", "tag", "category"]):
                continue

            # Build full URL
            full_url = href if href.startswith("http") else urljoin(self.page_url, href)

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Find description (sibling paragraph or parent container text)
            parent = link.parent
            if parent:
                # Try to find description in nearby elements
                desc_parts = []
                for sibling in parent.find_all(["p", "span", "div"], recursive=False)[:2]:
                    sibling_text = sibling.get_text(strip=True)
                    if sibling_text and len(sibling_text) > 10:
                        desc_parts.append(sibling_text)
                description = " ".join(desc_parts)[:500]
            else:
                description = ""

            article_candidates.append((text, full_url, description))

        # Deduplicate by title similarity and take top N
        seen_titles: set[str] = set()
        for title, url, desc in article_candidates[:self.max_items * 3]:
            # Simple dedup: skip very similar titles
            title_key = title[:30].lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            if len(articles) >= self.max_items:
                break

            articles.append(RawArticle(
                title=title[:200],
                url=canonicalize_url(url),
                description=desc[:500],
                source=self.source_name,
                content_type=self._content_type,
                priority=self._priority,
                metadata={
                    "feed_name": self._name,
                    "language": self.language,
                    "scraped": True,
                },
            ))

        logger.info(f"Scrape '{self._name}': found {len(articles)} articles")
        return articles


def create_rss_fetchers(config: dict) -> list[SourceProtocol]:
    """Create RSS fetchers from the sources configuration.

    Handles both RSS feeds and scraping-mode feeds (scrape: true).
    """
    fetchers: list[SourceProtocol] = []
    sources = config.get("sources", {})

    rss_feeds = sources.get("rss_feeds", [])
    for feed_cfg in rss_feeds:
        if not isinstance(feed_cfg, dict) or not feed_cfg.get("enabled", True):
            continue

        ct_str = feed_cfg.get("content_type", "industry")
        priority_str = feed_cfg.get("priority", "core")
        try:
            priority = SourcePriority(priority_str)
        except ValueError:
            priority = SourcePriority.CORE

        is_scrape = feed_cfg.get("scrape", False)

        if is_scrape:
            fetchers.append(ScrapingFetcher(
                name=feed_cfg["name"],
                page_url=feed_cfg["url"],
                content_type=CONTENT_TYPE_MAP.get(ct_str, ContentType.INDUSTRY),
                priority=priority,
                language=feed_cfg.get("language", "zh"),
                max_items=feed_cfg.get("max_items", 20),
                timeout=config.get("global", {}).get("request_timeout", 30),
                user_agent=config.get("global", {}).get(
                    "user_agent", "AI-Info-Collector/1.0"
                ),
            ))
        else:
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
        if src_cfg.get("repos") or src_cfg.get("topics") or src_cfg.get("tools"):
            continue
        if src_cfg.get("endpoint") or src_cfg.get("since"):
            continue
        if src_name in ("product_hunt", "hacker_news", "mcp_pulse",
                        "claude_plugins", "framework_watch", "coding_tools",
                        "oss_models", "official_blogs", "github_trending",
                        "huggingface_papers", "rss_feeds", "global"):
            continue

        ct_str = src_cfg.get("content_type", "industry")
        priority_str = src_cfg.get("priority", "core")
        try:
            priority = SourcePriority(priority_str)
        except ValueError:
            priority = SourcePriority.CORE

        is_scrape = src_cfg.get("scrape", False)
        if is_scrape:
            fetchers.append(ScrapingFetcher(
                name=src_name,
                page_url=src_cfg["url"],
                content_type=CONTENT_TYPE_MAP.get(ct_str, ContentType.INDUSTRY),
                priority=priority,
                language=src_cfg.get("language", "zh"),
                max_items=src_cfg.get("max_items", 15),
                timeout=config.get("global", {}).get("request_timeout", 30),
                user_agent=config.get("global", {}).get(
                    "user_agent", "AI-Info-Collector/1.0"
                ),
            ))
        else:
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

    return fetchers
