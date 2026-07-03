"""
Product Hunt AI category aggregator.

Uses Product Hunt's GraphQL API (requires PH_DEV_TOKEN).
Fetches the most-voted posts in the AI topic.
"""

import logging
from datetime import datetime, timezone

import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

PH_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

POSTS_QUERY = """
query($topic: String!, $first: Int!) {
  topic(slug: $topic) {
    posts(first: $first, order: VOTES) {
      edges {
        node {
          id
          name
          tagline
          description
          url
          votesCount
          commentsCount
          createdAt
          website
          thumbnail {
            url
          }
        }
      }
    }
  }
}
"""


class ProductHuntSource(SourceProtocol):
    """Fetches trending AI products from Product Hunt."""

    def __init__(
        self,
        api_token: str,
        topic_slug: str = "ai",
        max_items: int = 20,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.api_token = api_token
        self.topic_slug = topic_slug
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "product_hunt"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.DEV_TOOL

    async def fetch(self) -> list[RawArticle]:
        """Fetch AI products from Product Hunt."""
        if not self.api_token:
            logger.warning("Product Hunt: no API token configured, skipping")
            return []

        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                response = await client.post(
                    PH_GRAPHQL_URL,
                    json={
                        "query": POSTS_QUERY,
                        "variables": {
                            "topic": self.topic_slug,
                            "first": self.max_items,
                        },
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.error(f"Product Hunt fetch failed: {e}")
            return []

        posts: list[dict] = []
        try:
            edges = (
                data.get("data", {})
                .get("topic", {})
                .get("posts", {})
                .get("edges", [])
            )
            for edge in edges:
                node = edge.get("node", {})
                if node:
                    posts.append(node)
        except Exception as e:
            logger.error(f"Product Hunt response parse failed: {e}")
            return []

        articles: list[RawArticle] = []
        for post in posts:
            try:
                title = f"{post.get('name', 'Unknown')} — {post.get('tagline', '')}"
                url = post.get("url") or post.get("website", "")
                if not url:
                    continue

                published_at = None
                if post.get("createdAt"):
                    try:
                        published_at = datetime.fromisoformat(
                            str(post["createdAt"]).replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

                articles.append(RawArticle(
                    title=title.strip()[:200],
                    url=canonicalize_url(url),
                    description=(post.get("description") or post.get("tagline", ""))[:500],
                    source=self.source_name,
                    content_type=ContentType.DEV_TOOL,
                    metadata={
                        "ph_id": post.get("id", ""),
                        "votes": post.get("votesCount", 0),
                        "comments": post.get("commentsCount", 0),
                        "website": post.get("website", ""),
                    },
                    published_at=published_at,
                ))
            except Exception as e:
                logger.debug(f"Skipping PH product: {e}")
                continue

        logger.info(f"Product Hunt: fetched {len(articles)} AI products")
        return articles
