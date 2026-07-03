"""
Agent framework release watcher.

Monitors GitHub releases for specified AI agent frameworks.
Uses GitHub's public API — no auth required for public repos
(GITHUB_TOKEN optional for higher rate limits).
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


class FrameworkWatchSource(SourceProtocol):
    """Monitors GitHub releases for agent frameworks."""

    def __init__(
        self,
        repos: list[str],
        lookback_days: int = 1,
        github_token: str = "",
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.repos = repos
        self.lookback_days = lookback_days
        self.github_token = github_token
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "framework_watch"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.AGENT_FRAMEWORK

    async def _fetch_releases(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[dict]:
        """Fetch recent releases for a single repo."""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        url = f"{GITHUB_API_URL}/repos/{repo}/releases?per_page=5"
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                logger.debug(f"Framework watch: repo {repo} not found")
                return []
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Framework watch: failed to fetch {repo}: {e}")
            return []

    async def fetch(self) -> list[RawArticle]:
        """Check all watched repos for recent releases."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        articles: list[RawArticle] = []

        async with create_http_client(self.timeout, self.user_agent) as client:
            for repo in self.repos:
                try:
                    releases = await self._fetch_releases(client, repo)
                except Exception:
                    continue

                for release in releases:
                    if not isinstance(release, dict):
                        continue

                    # Parse release date
                    published_at_str = release.get("published_at") or release.get("created_at", "")
                    if not published_at_str:
                        continue

                    try:
                        published_at = datetime.fromisoformat(
                            published_at_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        continue

                    # Skip old releases
                    if published_at < cutoff_date:
                        continue

                    # Skip pre-releases unless they're significant
                    is_prerelease = release.get("prerelease", False)
                    tag = release.get("tag_name", "")

                    title = f"[{repo}] {tag}: {release.get('name', 'Release')}"
                    body = release.get("body", "") or ""
                    description = body[:500] if body else f"New release: {tag}"

                    articles.append(RawArticle(
                        title=title[:200],
                        url=canonicalize_url(
                            release.get("html_url", f"https://github.com/{repo}/releases/tag/{tag}")
                        ),
                        description=description,
                        source=self.source_name,
                        content_type=ContentType.AGENT_FRAMEWORK,
                        published_at=published_at,
                        metadata={
                            "repo": repo,
                            "tag": tag,
                            "is_prerelease": is_prerelease,
                            "release_name": release.get("name", ""),
                        },
                    ))

        logger.info(f"Framework Watch: found {len(articles)} recent releases")
        return articles
