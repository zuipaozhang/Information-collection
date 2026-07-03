"""
Hacker News aggregator.

Uses the HN Firebase API (free, no auth) to fetch top stories
and filter them by AI-related keywords. Only includes posts
with score > min_score to reduce noise.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle, SourcePriority

logger = logging.getLogger(__name__)

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsSource(SourceProtocol):
    """Fetches AI-related stories from Hacker News."""

    def __init__(
        self,
        ai_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        story_type: str = "top",
        max_fetch_ids: int = 100,
        min_score: int = 100,
        max_items: int = 20,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.ai_keywords = [kw.lower() for kw in (ai_keywords or [])]
        self.exclude_keywords = exclude_keywords or []
        self.story_type = story_type  # "top", "new", "best"
        self.max_fetch_ids = max_fetch_ids
        self.min_score = min_score
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "hacker_news"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.INDUSTRY

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.DEGRADED

    def _is_ai_relevant(self, title: str) -> bool:
        """Check if title matches AI keywords."""
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in self.ai_keywords)

    def _should_exclude(self, title: str) -> bool:
        """Exclude posts matching exclusion patterns (Ask HN, hiring, etc.)."""
        for pattern in self.exclude_keywords:
            if pattern.lower() in title.lower():
                return True
        return False

    async def _fetch_item(
        self, client: httpx.AsyncClient, item_id: int
    ) -> dict | None:
        """Fetch a single HN item."""
        try:
            response = await client.get(f"{HN_BASE_URL}/item/{item_id}.json")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def fetch(self) -> list[RawArticle]:
        """Fetch AI-related stories from HN."""
        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                # Get story IDs
                response = await client.get(
                    f"{HN_BASE_URL}/{self.story_type}stories.json"
                )
                response.raise_for_status()
                all_ids = response.json()[: self.max_fetch_ids]

                if not all_ids:
                    logger.warning("HN: no story IDs returned")
                    return []

                # Fetch items in parallel batches of 10
                items: list[dict] = []
                batch_size = 10
                for i in range(0, len(all_ids), batch_size):
                    batch = all_ids[i : i + batch_size]
                    tasks = [self._fetch_item(client, sid) for sid in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, dict) and result is not None:
                            items.append(result)
                    # Small delay between batches
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"HN fetch failed: {e}")
            return []

        # Filter and normalize
        articles: list[RawArticle] = []
        for item in items:
            if len(articles) >= self.max_items:
                break

            title = (item.get("title") or "").strip()
            if not title:
                continue

            # Apply exclusion filters
            if self._should_exclude(title):
                continue

            # Apply AI relevance filter
            if not self._is_ai_relevant(title):
                continue

            # Apply score filter
            score = item.get("score", 0)
            if score < self.min_score:
                continue

            # Skip non-story types
            if item.get("type") != "story":
                continue

            url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"

            # Parse time
            published_at = None
            if item.get("time"):
                try:
                    published_at = datetime.fromtimestamp(item["time"], tz=timezone.utc)
                except Exception:
                    pass

            content_type = ContentType.INDUSTRY
            # Categorize high-score or deep content as potential guides
            if score >= 200 and any(
                kw in title.lower()
                for kw in ["guide", "how", "building", "lesson", "pattern", "best practice"]
            ):
                content_type = ContentType.GUIDE

            articles.append(RawArticle(
                title=title,
                url=canonicalize_url(url),
                description=(
                    f"Score: {score}, Comments: {item.get('descendants', 0)}. "
                    f"By: {item.get('by', 'unknown')}."
                ),
                source=self.source_name,
                content_type=content_type,
                priority=self.priority,
                published_at=published_at,
                metadata={
                    "hn_id": item.get("id"),
                    "score": score,
                    "comments": item.get("descendants", 0),
                    "author": item.get("by", ""),
                },
            ))

        logger.info(
            f"Hacker News: fetched {len(articles)} AI stories (min score: {self.min_score})"
        )
        return articles
