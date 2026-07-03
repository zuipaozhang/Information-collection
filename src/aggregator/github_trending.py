"""
GitHub Trending scraper.

Scrapes https://github.com/trending for AI/ML-related repositories.
No API key required — uses HTML parsing with BeautifulSoup.
"""

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"


class GitHubTrendingSource(SourceProtocol):
    """Scrapes GitHub Trending for AI-related repositories."""

    def __init__(
        self,
        ai_keywords: list[str] | None = None,
        since: str = "daily",
        max_items: int = 25,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.ai_keywords = ai_keywords or []
        self.since = since  # "daily" or "weekly"
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

        # Build search URL for "since" period + Python as a proxy language
        self.url = f"{GITHUB_TRENDING_URL}?since={since}"

    @property
    def source_name(self) -> str:
        return "github_trending"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.DEV_TOOL

    def _is_ai_relevant(self, repo_name: str, description: str, language: str) -> bool:
        """Check if a repo is AI-related by matching keywords."""
        text = f"{repo_name} {description}".lower()
        for keyword in self.ai_keywords:
            if keyword.lower() in text:
                return True
        # Also match common AI languages
        ai_languages = {"Python", "Jupyter Notebook", "Rust", "TypeScript"}
        if language in ai_languages and any(
            kw in text for kw in ["ai", "llm", "ml", "model", "neural", "gpt"]
        ):
            return True
        return False

    def _parse_stars(self, text: str) -> int:
        """Parse '1,234' or '1.2k' style star counts to integers."""
        text = text.strip().lower().replace(",", "")
        if text.endswith("k"):
            try:
                return int(float(text[:-1]) * 1000)
            except ValueError:
                return 0
        try:
            return int(text)
        except ValueError:
            return 0

    async def fetch(self) -> list[RawArticle]:
        """Fetch and parse GitHub Trending."""
        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                response = await client.get(self.url)
                response.raise_for_status()
                html = response.text
        except Exception as e:
            logger.error(f"GitHub Trending fetch failed: {e}")
            return []

        try:
            soup = BeautifulSoup(html, "lxml")
            repos = soup.find_all("article", class_="Box-row")
        except Exception as e:
            logger.error(f"GitHub Trending parse failed: {e}")
            return []

        articles: list[RawArticle] = []
        for repo in repos:
            if len(articles) >= self.max_items:
                break

            try:
                # Extract repo name from h2
                h2 = repo.find("h2", class_="h3 lh-condensed")
                if not h2:
                    continue
                name_parts = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
                # Clean up the "owner / repo" format
                repo_name = re.sub(r"\s+", "", name_parts.replace("/", "/").strip())

                # Extract description
                desc_p = repo.find("p", class_="col-9")
                description = desc_p.get_text(strip=True) if desc_p else ""

                # Extract language
                lang_span = repo.find("span", itemprop="programmingLanguage")
                language = lang_span.get_text(strip=True) if lang_span else "Unknown"

                # Check AI relevance
                if not self._is_ai_relevant(repo_name, description, language):
                    continue

                # Extract URL
                link_tag = h2.find("a")
                if not link_tag:
                    continue
                relative_url = link_tag.get("href", "")
                repo_url = f"https://github.com{relative_url}"

                # Extract stars
                stars = 0
                star_link = repo.find("a", href=re.compile(r"/stargazers"))
                if star_link:
                    stars = self._parse_stars(star_link.get_text(strip=True))

                # Extract today's stars
                today_stars = 0
                for span in repo.find_all("span", class_="d-inline-block"):
                    text = span.get_text(strip=True)
                    if "star" in text.lower():
                        nums = re.findall(r"[\d,]+", text)
                        if nums:
                            today_stars = self._parse_stars(nums[0])

                articles.append(RawArticle(
                    title=f"{repo_name}: {description[:100]}" if description else repo_name,
                    url=canonicalize_url(repo_url),
                    description=description[:500],
                    source=self.source_name,
                    content_type=self.default_content_type,
                    metadata={
                        "repo_name": repo_name,
                        "repo_url": repo_url,
                        "stars": stars,
                        "stars_today": today_stars,
                        "language": language,
                    },
                ))
            except Exception as e:
                logger.debug(f"Skipping GitHub Trending repo: {e}")
                continue

        logger.info(f"GitHub Trending: fetched {len(articles)} AI-relevant repos")
        return articles
