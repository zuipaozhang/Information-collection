"""
PulseMCP aggregator.

Tracks new and trending MCP servers from the PulseMCP ecosystem.
Since the PulseMCP API now requires authentication, we use:
  1. dev.to RSS feed for community MCP posts
  2. Scraping pulsemcp.com/servers for new arrivals
"""

import logging
import re
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

# PulseMCP community posts (dev.to tag) — free, no auth
DEVTO_MCP_RSS = "https://dev.to/feed/tag/mcp"
# PulseMCP servers page for scraping new arrivals
PULSEMCP_SERVERS_URL = "https://www.pulsemcp.com/servers"


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

    async def _scrape_servers_page(self, client: httpx.AsyncClient) -> list[RawArticle]:
        """Scrape pulsemcp.com/servers for new MCP server listings."""
        articles: list[RawArticle] = []
        try:
            response = await client.get(PULSEMCP_SERVERS_URL)
            if response.status_code != 200:
                logger.debug(f"PulseMCP servers page returned {response.status_code}")
                return articles

            soup = BeautifulSoup(response.text, "lxml")

            # Look for server cards — common patterns on PulseMCP
            # Each server entry is typically a link card with name and description
            server_cards = soup.find_all(["a", "div"], class_=re.compile(
                r"(server|card|entry|item)", re.I
            ))

            count = 0
            for card in server_cards[:self.max_items * 2]:
                if count >= self.max_items:
                    break

                # Find name (usually in an h2/h3 or strong tag)
                name_tag = card.find(["h2", "h3", "strong", "span"], class_=re.compile(r"(name|title)", re.I))
                if not name_tag:
                    name_tag = card.find(["h2", "h3"])

                name = name_tag.get_text(strip=True) if name_tag else ""
                if not name or len(name) < 3:
                    continue

                # Find description
                desc_tag = card.find(["p", "span", "div"], class_=re.compile(r"(desc|summary)", re.I))
                description = desc_tag.get_text(strip=True) if desc_tag else ""

                # Find link
                url = ""
                if card.name == "a" and card.get("href"):
                    href = card["href"]
                    url = href if href.startswith("http") else f"https://pulsemcp.com{href}"
                else:
                    link = card.find("a", href=True)
                    if link:
                        href = link["href"]
                        url = href if href.startswith("http") else f"https://pulsemcp.com{href}"

                # Build install command from name
                server_slug = re.sub(r"[^a-zA-Z0-9-]", "", name.lower().replace(" ", "-"))[:30]
                install_cmd = None
                if "mcp" in name.lower():
                    install_cmd = f"npx @anthropic-ai/mcp-server-{server_slug}"

                articles.append(RawArticle(
                    title=f"MCP Server: {name}",
                    url=canonicalize_url(url) if url else f"https://pulsemcp.com/servers",
                    description=description[:500],
                    source=self.source_name,
                    content_type=ContentType.MCP_SERVER,
                    metadata={
                        "source": "pulsemcp_scraped",
                        "server_name": name,
                    },
                ))
                if install_cmd:
                    articles[-1].metadata["install_command"] = install_cmd
                count += 1

        except Exception as e:
            logger.debug(f"PulseMCP scraping failed: {e}")

        return articles

    async def _fetch_community_posts(self, client: httpx.AsyncClient) -> list[RawArticle]:
        """Fetch MCP-related posts from dev.to RSS."""
        articles: list[RawArticle] = []
        try:
            response = await client.get(DEVTO_MCP_RSS)
            feed = feedparser.parse(response.text)

            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

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
            # Scrape servers page for new arrivals
            scraped = await self._scrape_servers_page(client)
            articles.extend(scraped)

            # Fetch community posts from dev.to
            community = await self._fetch_community_posts(client)
            articles.extend(community)

        logger.info(
            f"PulseMCP: fetched {len(articles)} items "
            f"({len(scraped)} scraped + {len(community)} community)"
        )
        return articles
