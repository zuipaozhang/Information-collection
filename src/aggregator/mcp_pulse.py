"""
PulseMCP aggregator.

Tracks new and trending MCP servers from the PulseMCP ecosystem.
Fetches from PulseMCP's public API and community newsletter (dev.to RSS).
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

PULSEMCP_TRENDING_URL = "https://pulsemcp.com/api/trending"
# PulseMCP community posts (dev.to tag)
DEVTO_MCP_RSS = "https://dev.to/feed/tag/mcp"


class MCPPulseSource(SourceProtocol):
    """Tracks trending and new MCP servers from PulseMCP."""

    def __init__(
        self,
        max_items: int = 20,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "mcp_pulse"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.MCP_SERVER

    async def _fetch_trending(self, client: httpx.AsyncClient) -> list[RawArticle]:
        """Fetch trending MCP servers from PulseMCP API."""
        articles: list[RawArticle] = []
        try:
            response = await client.get(PULSEMCP_TRENDING_URL)
            if response.status_code != 200:
                logger.warning(f"PulseMCP trending returned {response.status_code}")
                return articles

            data = response.json()
            servers = data if isinstance(data, list) else data.get("servers", data.get("data", []))

            for server in servers[: self.max_items]:
                if not isinstance(server, dict):
                    continue

                name = server.get("name") or server.get("title", "")
                if not name:
                    continue

                description = server.get("description") or server.get("summary", "")
                url = server.get("url") or server.get("github_url") or server.get("website", "")

                # Build install command if available
                install_cmd = server.get("install_command") or server.get("npm_package", "")
                metadata = {
                    "source": "pulsemcp_trending",
                    "category": server.get("category", ""),
                }
                if install_cmd:
                    metadata["install_command"] = install_cmd

                articles.append(RawArticle(
                    title=f"MCP Server: {name}",
                    url=canonicalize_url(url) if url else "",
                    description=description[:500],
                    source=self.source_name,
                    content_type=ContentType.MCP_SERVER,
                    metadata=metadata,
                ))
        except Exception as e:
            logger.error(f"PulseMCP trending fetch failed: {e}")

        return articles

    async def _fetch_community_posts(self, client: httpx.AsyncClient) -> list[RawArticle]:
        """Fetch MCP-related posts from dev.to RSS."""
        articles: list[RawArticle] = []
        try:
            import feedparser
            response = await client.get(DEVTO_MCP_RSS)
            feed = feedparser.parse(response.text)

            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Parse published date
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                articles.append(RawArticle(
                    title=title,
                    url=canonicalize_url(entry.get("link", "")),
                    description=(entry.get("summary", "") or "")[:500],
                    source=self.source_name,
                    content_type=ContentType.MCP_SERVER,
                    published_at=published_at,
                    metadata={"source": "devto_mcp"},
                ))
        except Exception as e:
            logger.debug(f"PulseMCP community posts: {e}")

        return articles

    async def fetch(self) -> list[RawArticle]:
        """Fetch trending and new MCP servers."""
        articles: list[RawArticle] = []

        async with create_http_client(self.timeout, self.user_agent) as client:
            # Fetch trending servers
            trending = await self._fetch_trending(client)
            articles.extend(trending)

            # Fetch community posts
            community = await self._fetch_community_posts(client)
            articles.extend(community)

        logger.info(f"PulseMCP: fetched {len(articles)} items ({len(trending)} trending + {len(community)} community)")
        return articles
