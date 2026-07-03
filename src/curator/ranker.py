"""
Ranking and selection logic.

Ranks CuratedArticles by weighted_score with diversity bonuses,
then selects the top N for inclusion in the digest.

Key features:
- Tool-weighted scoring (mcp_server/claude_skill/coding_tool get bonus)
- Category diversity (penalize consecutive same-category items)
- Source diversity (cap max items from same source)
- Auxiliary source exclusion from final ranking
"""

import logging
from collections import defaultdict

from src.curator.models import (
    INSTALLABLE_TYPES,
    ContentType,
    CuratedArticle,
    SourcePriority,
)

logger = logging.getLogger(__name__)


class Ranker:
    """Ranks and selects curated articles for digest inclusion."""

    def __init__(
        self,
        max_per_source: int = 3,
        diversity_penalty: float = 0.2,
    ):
        self.max_per_source = max_per_source
        self.diversity_penalty = diversity_penalty

    def rank(self, articles: list[CuratedArticle]) -> list[CuratedArticle]:
        """
        Rank articles by weighted score with diversity bonuses.

        Excludes auxiliary source articles from ranking.
        """
        if not articles:
            return []

        # Filter out auxiliary sources
        rankable = [
            a for a in articles
            if a.original.priority != SourcePriority.AUXILIARY
        ]

        # Separate installable tools — they always rank high
        installable = [a for a in rankable if a.content_type in INSTALLABLE_TYPES]
        non_installable = [a for a in rankable if a.content_type not in INSTALLABLE_TYPES]

        # Sort each group by weighted_score descending
        installable.sort(key=lambda a: a.weighted_score, reverse=True)
        non_installable.sort(key=lambda a: a.weighted_score, reverse=True)

        # Interleave: apply diversity within each group
        ranked = (
            self._apply_diversity(installable)
            + self._apply_diversity(non_installable)
        )

        return ranked

    def _apply_diversity(
        self, articles: list[CuratedArticle]
    ) -> list[CuratedArticle]:
        """
        Apply category and source diversity to ranked list.

        Uses a greedy algorithm: picks highest-scored item, then
        prefers items from different categories and sources.
        """
        if len(articles) <= 1:
            return articles

        ranked: list[CuratedArticle] = []
        remaining = list(articles)
        source_counts: dict[str, int] = defaultdict(int)

        while remaining:
            best_idx = 0
            best_score = -1.0

            for idx, article in enumerate(remaining):
                # Base score
                score = article.weighted_score

                # Source cap: if source already has max entries, heavily penalize
                source_count = source_counts.get(article.original.source, 0)
                if source_count >= self.max_per_source:
                    score -= 2.0  # Heavy penalty, nearly excludes

                # Category diversity: if we already have items from this category,
                # apply slight penalty
                if ranked:
                    last_categories = set(ranked[-1].categories)
                    article_categories = set(article.categories)
                    if last_categories & article_categories:
                        score -= self.diversity_penalty

                if score > best_score:
                    best_score = score
                    best_idx = idx

            # Select the best
            selected = remaining.pop(best_idx)
            ranked.append(selected)
            source_counts[selected.original.source] += 1

        return ranked

    def select_top(
        self, articles: list[CuratedArticle], n: int
    ) -> list[CuratedArticle]:
        """
        Rank and select the top N articles for a digest.

        Ensures at least 40% of selections are installable tools
        when available.
        """
        ranked = self.rank(articles)

        if len(ranked) <= n:
            return ranked

        # Ensure tool diversity: at least 40% tools when available
        installable = [a for a in ranked if a.content_type in INSTALLABLE_TYPES]
        non_installable = [a for a in ranked if a.content_type not in INSTALLABLE_TYPES]

        min_tools = min(len(installable), max(1, int(n * 0.4)))
        min_non_tools = n - min_tools

        selected = installable[:min_tools] + non_installable[:min_non_tools]

        # If we don't have enough non-tools, fill with more tools
        if len(selected) < n and len(installable) > min_tools:
            selected += installable[min_tools : min_tools + (n - len(selected))]

        # Final sort by weighted_score within the selected set
        selected.sort(key=lambda a: a.weighted_score, reverse=True)

        logger.info(
            f"Selected top {len(selected)}: "
            f"{sum(1 for a in selected if a.content_type in INSTALLABLE_TYPES)} tools "
            f"({min_tools} min) + "
            f"{sum(1 for a in selected if a.content_type not in INSTALLABLE_TYPES)} content"
        )

        return selected[:n]
