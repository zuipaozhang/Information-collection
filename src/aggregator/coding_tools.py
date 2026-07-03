"""
AI coding tool changelog watcher.

Monitors Claude Code and Cursor for new releases and features.
Uses GitHub Releases API for Claude Code, and web scraping for Cursor changelog.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


class CodingToolsSource(SourceProtocol):
    """Monitors AI coding tools for updates."""

    def __init__(
        self,
        github_token: str = "",
        lookback_days: int = 1,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.github_token = github_token
        self.lookback_days = lookback_days
        self.timeout = timeout
        self.user_agent = user_agent

        # Tools to watch
        self.tools = [
            {"name": "Claude Code", "repo": "anthropics/claude-code", "type": "github"},
            {"name": "Cursor", "url": "https://www.cursor.com/changelog", "type": "changelog"},
        ]

    @property
    def source_name(self) -> str:
        return "coding_tools"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.CODING_TOOL

    def _github_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    async def _fetch_github_releases(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[RawArticle]:
        """Fetch recent releases from a GitHub repo."""
        articles: list[RawArticle] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

        url = f"{GITHUB_API_URL}/repos/{repo}/releases?per_page=5"
        try:
            response = await client.get(url, headers=self._github_headers())
            if response.status_code != 200:
                logger.debug(f"Coding tools: {repo} returns {response.status_code}")
                return articles

            for release in response.json():
                if not isinstance(release, dict):
                    continue

                published_str = release.get("published_at", "")
                if not published_str:
                    continue
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except Exception:
                    continue

                if published_at < cutoff:
                    continue

                tag = release.get("tag_name", "")
                name = release.get("name", tag)
                is_prerelease = release.get("prerelease", False)

                body = (release.get("body") or "")[:800]

                # Extract install command
                install_cmd = None
                repo_lower = repo.lower()
                if "claude-code" in repo_lower:
                    install_cmd = "npm update @anthropic-ai/claude-code"

                articles.append(RawArticle(
                    title=f"[Claude Code] {name}",
                    url=canonicalize_url(release.get("html_url", "")),
                    description=body[:500],
                    source=self.source_name,
                    content_type=ContentType.CODING_TOOL,
                    published_at=published_at,
                    metadata={
                        "repo": repo,
                        "tag": tag,
                        "is_prerelease": is_prerelease,
                    },
                ))

                # Pre-compute install command for LLM
                if install_cmd:
                    articles[-1].metadata["install_command"] = install_cmd
        except Exception as e:
            logger.debug(f"Coding tools: {repo} error: {e}")

        return articles

    async def _fetch_cursor_changelog(
        self, client: httpx.AsyncClient
    ) -> list[RawArticle]:
        """Scrape Cursor changelog page for recent updates."""
        articles: list[RawArticle] = []
        try:
            response = await client.get("https://www.cursor.com/changelog")
            if response.status_code != 200:
                logger.debug(f"Cursor changelog returned {response.status_code}")
                return articles

            soup = BeautifulSoup(response.text, "lxml")

            # Cursor changelog entries — look for version headers and update blocks
            # The structure varies, so we try common patterns
            entries = soup.find_all(["article", "section", "div"], class_=True)
            count = 0
            for entry in entries[:10]:
                # Look for version patterns
                text = entry.get_text(strip=True)
                if not text or len(text) < 20:
                    continue

                # Check if it looks like a changelog entry (has version number)
                import re
                version_match = re.search(r'(?:version|v\.?)\s*(\d+\.\d+)', text, re.IGNORECASE)
                if not version_match:
                    # Also look for date patterns suggesting a recent update
                    if not re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', text):
                        continue

                title = text.split("\n")[0][:200] if "\n" in text else text[:200]
                description = text[:500]

                # Try to find an anchor link
                link_tag = entry.find("a")
                url = ""
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    url = href if href.startswith("http") else f"https://www.cursor.com{href}"
                else:
                    url = "https://www.cursor.com/changelog"

                articles.append(RawArticle(
                    title=f"[Cursor] {title}",
                    url=canonicalize_url(url),
                    description=description,
                    source=self.source_name,
                    content_type=ContentType.CODING_TOOL,
                    metadata={"tool": "Cursor", "url": "https://www.cursor.com/changelog"},
                ))
                count += 1
                if count >= 3:
                    break

        except Exception as e:
            logger.debug(f"Cursor changelog parse error: {e}")

        return articles

    async def fetch(self) -> list[RawArticle]:
        """Check all coding tools for updates."""
        articles: list[RawArticle] = []

        async with create_http_client(self.timeout, self.user_agent) as client:
            # Check GitHub-based tools
            for tool in self.tools:
                if tool["type"] == "github":
                    releases = await self._fetch_github_releases(client, tool["repo"])
                    articles.extend(releases)
                elif tool["type"] == "changelog":
                    entries = await self._fetch_cursor_changelog(client)
                    articles.extend(entries)

        logger.info(f"Coding Tools: found {len(articles)} updates")
        return articles
