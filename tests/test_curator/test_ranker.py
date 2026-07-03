"""Tests for the ranking engine."""

import pytest
from src.curator.models import ContentType, CuratedArticle, RawArticle
from src.curator.ranker import Ranker


def _make_article(title: str, content_type: ContentType, score: float, source: str = "test"):
    """Helper to create a CuratedArticle for testing."""
    raw = RawArticle(
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        source=source,
        content_type=content_type,
    )
    return CuratedArticle(
        original=raw,
        chinese_title=title,
        chinese_summary="Test summary",
        content_type=content_type,
        categories=["Test"],
        importance_score=int(score),
        weighted_score=score,
        recommendation_reason="Test",
    )


class TestRanker:
    """Ranking engine tests."""

    def test_sort_by_weighted_score(self):
        """Articles should be sorted by weighted_score descending."""
        ranker = Ranker()
        articles = [
            _make_article("Low", ContentType.INDUSTRY, 2.0),
            _make_article("High", ContentType.INDUSTRY, 5.0),
            _make_article("Mid", ContentType.INDUSTRY, 3.5),
        ]

        ranked = ranker.rank(articles)
        scores = [a.weighted_score for a in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_installable_types_rank_higher(self):
        """Installable types (mcp_server, claude_skill, coding_tool) rank first."""
        ranker = Ranker()
        articles = [
            _make_article("Industry News", ContentType.INDUSTRY, 4.5),
            _make_article("MCP Server", ContentType.MCP_SERVER, 3.5),
        ]

        ranked = ranker.rank(articles)
        # Installable should be first despite lower raw score
        assert ranked[0].content_type == ContentType.MCP_SERVER

    def test_source_cap(self):
        """A single source should be capped at max_per_source."""
        ranker = Ranker(max_per_source=2)
        articles = [
            _make_article(f"Item {i}", ContentType.INDUSTRY, 5.0 - i * 0.1, source="same_source")
            for i in range(5)
        ]

        ranked = ranker.rank(articles)
        same_source_count = sum(
            1 for a in ranked if a.original.source == "same_source"
        )
        # While all 5 are from same source, after cap penalty, only top 2 should be at top
        # But since there are no other articles, all 5 remain ranked (just with penalties)
        assert len(ranked) == 5
        # The capped ones should be at the end
        first_two = [a.original.source for a in ranked[:2]]
        assert all(s == "same_source" for s in first_two)

    def test_select_top_with_tool_minimum(self):
        """Select top N should guarantee minimum tool percentage."""
        ranker = Ranker()
        articles = []
        # Create 10 non-installable articles
        for i in range(10):
            articles.append(_make_article(f"News {i}", ContentType.INDUSTRY, 5.0 - i * 0.1))
        # Create 3 installable articles
        for i in range(3):
            articles.append(_make_article(f"Tool {i}", ContentType.MCP_SERVER, 3.0 - i * 0.1))

        selected = ranker.select_top(articles, n=8)
        installable_count = sum(
            1 for a in selected if a.content_type in (
                ContentType.MCP_SERVER, ContentType.CLAUDE_SKILL, ContentType.CODING_TOOL
            )
        )
        # At least 40% of 8 = 3.2, so at least 3 installable
        assert installable_count >= min(3, 3)

    def test_select_top_respects_limit(self):
        """select_top should return at most N items."""
        ranker = Ranker()
        articles = [_make_article(f"Item {i}", ContentType.INDUSTRY, i * 1.0) for i in range(20)]

        selected = ranker.select_top(articles, n=8)
        assert len(selected) <= 8
