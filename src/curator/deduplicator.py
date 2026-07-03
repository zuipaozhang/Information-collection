"""
Multi-stage article deduplication engine.

Stages:
  1. Exact URL match against seen_urls.json
  2. URL canonicalization (strip tracking params, normalize)
  3. Title fuzzy matching (thefuzz) between items from different sources
  4. Cross-source reference extraction (DOI, arXiv ID, GitHub repo)
"""

import logging
import re
from typing import Any

from thefuzz import fuzz

from src.aggregator.base import canonicalize_url
from src.curator.models import RawArticle
from src.state.manager import StateManager

logger = logging.getLogger(__name__)

# Minimum fuzzy ratio for two titles to be considered duplicates
FUZZY_TITLE_THRESHOLD = 85

# Patterns for cross-source reference extraction
ARXIV_ID_PATTERN = re.compile(r"(?:arxiv\.org/abs/|arxiv:)(\d{4}\.\d{4,})", re.IGNORECASE)
DOI_PATTERN = re.compile(r"(?:doi\.org/|DOI:\s*)(10\.\d{4,}/[^\s]+)", re.IGNORECASE)
GITHUB_REPO_PATTERN = re.compile(r"github\.com/([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)", re.IGNORECASE)


class Deduplicator:
    """Deduplicates articles across multiple sources."""

    def __init__(self, state_manager: StateManager):
        self.state = state_manager

    def deduplicate(
        self,
        articles: list[RawArticle],
        mark_seen: bool = True,
    ) -> list[RawArticle]:
        """
        Deduplicate a list of RawArticles.

        Returns only unique articles. Optionally marks seen URLs
        in the state manager.
        """
        if not articles:
            return []

        # Stage 1 & 2: Check against seen URLs with canonicalization
        unique: list[RawArticle] = []
        seen_urls: set[str] = set()

        for article in articles:
            canonical = canonicalize_url(article.url)

            # Check against state (historical dedup)
            if self.state.is_seen(canonical):
                logger.debug(f"Dedup (seen): {canonical[:80]}")
                continue

            # Check against current batch
            if canonical in seen_urls:
                logger.debug(f"Dedup (batch): {canonical[:80]}")
                continue

            seen_urls.add(canonical)
            unique.append(article)

            # Mark as seen in state
            if mark_seen:
                self.state.mark_as_seen(
                    canonical_url=canonical,
                    source=article.source,
                    content_type=article.content_type.value,
                )

        logger.info(f"Dedup: {len(articles)} → {len(unique)} unique (stages 1-2)")

        # Stage 3: Title fuzzy matching within the current batch
        unique = self._fuzzy_title_dedup(unique)
        logger.info(f"Dedup: after fuzzy title → {len(unique)} unique (stage 3)")

        # Stage 4: Cross-source reference extraction
        unique = self._cross_source_dedup(unique)
        logger.info(f"Dedup: after cross-source → {len(unique)} unique (stage 4)")

        return unique

    def _fuzzy_title_dedup(self, articles: list[RawArticle]) -> list[RawArticle]:
        """
        Deduplicate by fuzzy title matching.

        Only compares items from DIFFERENT sources, since same-source
        duplicates should be caught by URL matching.
        """
        if len(articles) <= 1:
            return articles

        to_remove: set[int] = set()

        for i in range(len(articles)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(articles)):
                if j in to_remove:
                    continue
                # Only dedup items from different sources
                if articles[i].source == articles[j].source:
                    continue

                title_a = articles[i].title.lower().strip()
                title_b = articles[j].title.lower().strip()

                # Skip very short titles (prone to false positives)
                if len(title_a) < 15 or len(title_b) < 15:
                    continue

                ratio = fuzz.token_sort_ratio(title_a, title_b)
                if ratio >= FUZZY_TITLE_THRESHOLD:
                    # Keep the one with more metadata
                    meta_a = len(articles[i].description or "")
                    meta_b = len(articles[j].description or "")
                    if meta_a >= meta_b:
                        to_remove.add(j)
                    else:
                        to_remove.add(i)
                        break  # i is removed, stop comparing i

        return [a for idx, a in enumerate(articles) if idx not in to_remove]

    def _cross_source_dedup(self, articles: list[RawArticle]) -> list[RawArticle]:
        """
        Deduplicate by extracting canonical references (arXiv ID, DOI, GitHub repo)
        from titles and descriptions, then grouping articles that refer to the
        same underlying resource.
        """
        if len(articles) <= 1:
            return articles

        # Extract references from each article
        ref_map: dict[int, set[str]] = {}
        for idx, article in enumerate(articles):
            text = f"{article.title} {article.description}"
            refs: set[str] = set()

            # Find arXiv IDs
            for match in ARXIV_ID_PATTERN.finditer(text):
                refs.add(f"arxiv:{match.group(1)}")

            # Find DOIs
            for match in DOI_PATTERN.finditer(text):
                refs.add(f"doi:{match.group(1)}")

            # Find GitHub repos
            for match in GITHUB_REPO_PATTERN.finditer(text):
                refs.add(f"github:{match.group(1).lower()}")

            if refs:
                ref_map[idx] = refs

        # Find articles that share references
        to_remove: set[int] = set()
        for i in ref_map:
            if i in to_remove:
                continue
            for j in ref_map:
                if j <= i or j in to_remove:
                    continue
                if articles[i].source == articles[j].source:
                    continue

                # Check for overlapping references
                if ref_map[i] & ref_map[j]:
                    # Keep the one with more metadata
                    meta_a = len(articles[i].description or "")
                    meta_b = len(articles[j].description or "")
                    if meta_a >= meta_b:
                        to_remove.add(j)
                    else:
                        to_remove.add(i)
                        break

        return [a for idx, a in enumerate(articles) if idx not in to_remove]
