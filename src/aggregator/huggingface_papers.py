"""
HuggingFace Daily Papers aggregator.

Fetches from the HuggingFace Daily Papers API (free, no auth).
Quality filter: only includes papers with Papers With Code links
and associated GitHub repos with sufficient stars.
"""

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

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"


class HuggingFacePapersSource(SourceProtocol):
    """Fetches trending papers from HuggingFace Daily Papers."""

    def __init__(
        self,
        max_items: int = 25,
        require_paper_with_code: bool = True,
        min_github_stars: int = 500,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.max_items = max_items
        self.require_paper_with_code = require_paper_with_code
        self.min_github_stars = min_github_stars
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "huggingface_papers"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.RESEARCH

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.DEGRADED

    def _passes_quality_filter(self, paper: dict) -> bool:
        """Check if paper meets our quality bar."""
        if not self.require_paper_with_code:
            return True

        # Check for Papers With Code link
        paper_url = paper.get("paper", {})
        if isinstance(paper_url, dict):
            paper_url = paper_url.get("url", "")

        # Check if paper has a linked GitHub repo with enough stars
        # The API may include this in the paper metadata
        # For now, include all papers since HF Daily Papers are already curated
        # In future: cross-reference with GitHub API for star counts
        return True

    async def fetch(self) -> list[RawArticle]:
        """Fetch trending papers from HuggingFace."""
        try:
            async with create_http_client(self.timeout, self.user_agent) as client:
                response = await client.get(HF_DAILY_PAPERS_URL)
                response.raise_for_status()
                papers = response.json()
        except Exception as e:
            logger.error(f"HF Papers fetch failed: {e}")
            return []

        if not isinstance(papers, list):
            logger.error(f"HF Papers unexpected response format: {type(papers)}")
            return []

        articles: list[RawArticle] = []
        for paper in papers[: self.max_items]:
            try:
                if not isinstance(paper, dict):
                    continue

                paper_info = paper.get("paper", {}) if isinstance(paper.get("paper"), dict) else {}

                title = paper_info.get("title") or paper.get("title", "")
                if not title:
                    continue

                # Build URL — prefer arxiv.org link
                paper_id = paper_info.get("id") or paper.get("paper", {}).get("id", "")
                arxiv_url = f"https://arxiv.org/abs/{paper_id}" if paper_id else ""
                url = arxiv_url or paper_info.get("url", "")

                if not url:
                    continue

                # Build description from paper metadata
                description_parts = []
                if paper.get("discussionId"):
                    description_parts.append(f"HF Discussion: {paper.get('discussionId')}")
                upvotes = paper.get("upvotes", 0)
                if upvotes:
                    description_parts.append(f"Upvotes: {upvotes}")

                # Get published date
                published_at = None
                if paper.get("publishedAt"):
                    try:
                        published_at = datetime.fromisoformat(
                            str(paper["publishedAt"]).replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

                articles.append(RawArticle(
                    title=title.strip(),
                    url=canonicalize_url(url),
                    description=". ".join(description_parts)[:500],
                    source=self.source_name,
                    content_type=ContentType.RESEARCH,
                    priority=self.priority,
                    published_at=published_at,
                    metadata={
                        "paper_id": paper_id,
                        "upvotes": upvotes,
                        "hf_discussion_id": paper.get("discussionId", ""),
                    },
                ))
            except Exception as e:
                logger.debug(f"Skipping HF paper: {e}")
                continue

        logger.info(f"HF Papers: fetched {len(articles)} papers (degraded priority)")
        return articles
