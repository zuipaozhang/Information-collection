"""Tests for the deduplication engine."""

import pytest
from src.aggregator.base import canonicalize_url
from src.curator.deduplicator import Deduplicator
from src.curator.models import ContentType, RawArticle
from src.state.manager import StateManager


class TestCanonicalizeURL:
    """URL canonicalization tests."""

    def test_lowercase_scheme_host(self):
        assert canonicalize_url("HTTPS://GitHub.COM/OpenAI/gpt-5") == "https://github.com/OpenAI/gpt-5"

    def test_remove_utm_params(self):
        url = "https://example.com/page?utm_source=twitter&ref=homepage&id=123"
        result = canonicalize_url(url)
        assert "utm_source" not in result
        assert "ref=" not in result.lower() or "ref=" not in result
        assert "id=123" in result

    def test_remove_trailing_slash(self):
        assert canonicalize_url("https://github.com/openai/gpt-5/") == "https://github.com/openai/gpt-5"

    def test_remove_fragment(self):
        assert "#section" not in canonicalize_url("https://example.com#section")

    def test_remove_default_port(self):
        result = canonicalize_url("https://example.com:443/path")
        assert ":443" not in result


class TestDeduplicator:
    """Deduplication engine tests."""

    def test_exact_url_duplicate(self, temp_data_dir):
        """Two items with same URL should be deduplicated."""
        state = StateManager(temp_data_dir)
        dedup = Deduplicator(state)

        articles = [
            RawArticle(
                title="Same URL 1",
                url="https://example.com/article",
                source="source_a",
                content_type=ContentType.INDUSTRY,
            ),
            RawArticle(
                title="Same URL 2",
                url="https://example.com/article",
                source="source_b",
                content_type=ContentType.INDUSTRY,
            ),
        ]

        result = dedup.deduplicate(articles, mark_seen=False)
        assert len(result) == 1

    def test_utm_params_dedup(self, temp_data_dir):
        """URLs differing only by tracking params should be deduplicated."""
        state = StateManager(temp_data_dir)
        dedup = Deduplicator(state)

        articles = [
            RawArticle(
                title="With UTM",
                url="https://example.com/post?utm_source=twitter",
                source="source_a",
                content_type=ContentType.INDUSTRY,
            ),
            RawArticle(
                title="Without UTM",
                url="https://example.com/post",
                source="source_b",
                content_type=ContentType.INDUSTRY,
            ),
        ]

        result = dedup.deduplicate(articles, mark_seen=False)
        assert len(result) == 1

    def test_fuzzy_title_dedup(self, temp_data_dir):
        """Similar titles from different sources should be deduplicated."""
        state = StateManager(temp_data_dir)
        dedup = Deduplicator(state)

        articles = [
            RawArticle(
                title="OpenAI Releases GPT-5 With Groundbreaking Capabilities",
                url="https://techcrunch.com/gpt5",
                source="source_a",
                content_type=ContentType.MODEL_RELEASE,
            ),
            RawArticle(
                title="OpenAI Releases GPT-5 with Groundbreaking Capabilities!",
                url="https://different-source.com/gpt5",
                source="source_b",
                content_type=ContentType.MODEL_RELEASE,
            ),
        ]

        result = dedup.deduplicate(articles, mark_seen=False)
        assert len(result) <= 1

    def test_different_articles_not_deduped(self, temp_data_dir):
        """Completely different articles should not be deduplicated."""
        state = StateManager(temp_data_dir)
        dedup = Deduplicator(state)

        articles = [
            RawArticle(
                title="GPT-5 Released",
                url="https://example.com/gpt5",
                source="source_a",
                content_type=ContentType.MODEL_RELEASE,
            ),
            RawArticle(
                title="New Python Web Framework Launched",
                url="https://example.com/framework",
                source="source_b",
                content_type=ContentType.DEV_TOOL,
            ),
        ]

        result = dedup.deduplicate(articles, mark_seen=False)
        assert len(result) == 2

    def test_seen_url_filter(self, temp_data_dir):
        """Previously seen URLs should be filtered."""
        state = StateManager(temp_data_dir)
        state.mark_as_seen(
            "https://example.com/old-article",
            source="test",
            content_type="industry",
        )
        state.save_all()

        dedup = Deduplicator(state)

        articles = [
            RawArticle(
                title="Old Article",
                url="https://example.com/old-article",
                source="source_a",
                content_type=ContentType.INDUSTRY,
            ),
            RawArticle(
                title="New Article",
                url="https://example.com/new-article",
                source="source_b",
                content_type=ContentType.INDUSTRY,
            ),
        ]

        result = dedup.deduplicate(articles, mark_seen=False)
        assert len(result) == 1
        assert result[0].title == "New Article"
