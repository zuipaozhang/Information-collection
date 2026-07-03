"""
Claude Code plugins registry watcher.

Monitors the Claude Plugins Registry (GitHub repo) for new skill/plugin additions.
Uses GitHub API to detect new commits, releases, and trending plugins.
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


class ClaudePluginsSource(SourceProtocol):
    """Monitors Claude Code plugin registries for new additions."""

    def __init__(
        self,
        registry_repos: list[str],
        watch_interval_hours: int = 24,
        github_token: str = "",
        max_items: int = 15,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.registry_repos = registry_repos
        self.watch_interval_hours = watch_interval_hours
        self.github_token = github_token
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "claude_plugins"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.CLAUDE_SKILL

    def _build_github_headers(self) -> dict[str, str]:
        """Build headers for GitHub API requests."""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    async def _fetch_new_commits(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[dict]:
        """Fetch recent commits to a registry repo."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.watch_interval_hours)
        since_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{GITHUB_API_URL}/repos/{repo}/commits"
        params = {"since": since_iso, "per_page": 10}
        headers = self._build_github_headers()

        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Claude plugins: failed to fetch commits for {repo}: {e}")
            return []

    async def _fetch_latest_release(
        self, client: httpx.AsyncClient, repo: str
    ) -> dict | None:
        """Fetch the latest release for a repo."""
        url = f"{GITHUB_API_URL}/repos/{repo}/releases/latest"
        headers = self._build_github_headers()

        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def fetch(self) -> list[RawArticle]:
        """Check plugin registries for new content."""
        articles: list[RawArticle] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.watch_interval_hours)

        async with create_http_client(self.timeout, self.user_agent) as client:
            for repo in self.registry_repos:
                # Check new commits
                commits = await self._fetch_new_commits(client, repo)
                for commit in commits:
                    if not isinstance(commit, dict):
                        continue

                    commit_msg = commit.get("commit", {}).get("message", "")
                    sha = commit.get("sha", "")[:7]

                    # Extract skill/plugin name from commit message
                    first_line = commit_msg.split("\n")[0].strip()
                    if len(first_line) > 200:
                        first_line = first_line[:200]

                    commit_date_str = commit.get("commit", {}).get("committer", {}).get("date", "")
                    published_at = None
                    if commit_date_str:
                        try:
                            published_at = datetime.fromisoformat(
                                commit_date_str.replace("Z", "+00:00")
                            )
                        except Exception:
                            pass

                    html_url = commit.get("html_url", "")

                    articles.append(RawArticle(
                        title=f"[{repo.split('/')[-1]}] {first_line}",
                        url=canonicalize_url(html_url) if html_url else "",
                        description=f"New commit to {repo}: {first_line}",
                        source=self.source_name,
                        content_type=ContentType.CLAUDE_SKILL,
                        published_at=published_at,
                        metadata={
                            "repo": repo,
                            "sha": sha,
                            "author": commit.get("commit", {}).get("author", {}).get("name", ""),
                        },
                    ))

                # Check latest release
                release = await self._fetch_latest_release(client, repo)
                if release and isinstance(release, dict):
                    published_at_str = release.get("published_at", "")
                    if published_at_str:
                        try:
                            published_at = datetime.fromisoformat(
                                published_at_str.replace("Z", "+00:00")
                            )
                            if published_at >= cutoff:
                                tag = release.get("tag_name", "")
                                articles.append(RawArticle(
                                    title=f"[{repo.split('/')[-1]}] New Release: {tag}",
                                    url=canonicalize_url(release.get("html_url", "")),
                                    description=(release.get("body", "") or f"Release {tag}")[:500],
                                    source=self.source_name,
                                    content_type=ContentType.CLAUDE_SKILL,
                                    published_at=published_at,
                                    metadata={
                                        "repo": repo,
                                        "tag": tag,
                                        "release_name": release.get("name", ""),
                                    },
                                ))
                        except Exception:
                            pass

            # Limit results
            articles = articles[: self.max_items]

        logger.info(f"Claude Plugins: found {len(articles)} new items")
        return articles
