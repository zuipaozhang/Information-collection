"""Shared fixtures for all tests."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Ensure project root is in path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for state manager tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_raw_article():
    """A sample RawArticle for testing."""
    from src.curator.models import RawArticle, ContentType
    return RawArticle(
        title="Test MCP Server Released",
        url="https://github.com/test/mcp-server",
        description="A test MCP server for developers",
        source="mcp_pulse",
        content_type=ContentType.MCP_SERVER,
    )


@pytest.fixture
def sample_curated_article(sample_raw_article):
    """A sample CuratedArticle for testing."""
    from src.curator.models import CuratedArticle, ContentType
    return CuratedArticle(
        original=sample_raw_article,
        chinese_title="测试 MCP 服务器发布",
        chinese_summary="这是一个测试用的 MCP 服务器，可以连接到开发环境。",
        content_type=ContentType.MCP_SERVER,
        categories=["Developer Tools"],
        importance_score=4,
        weighted_score=5.0,
        recommendation_reason="可以直接安装使用",
        install_command="npx @test/mcp-server",
    )


@pytest.fixture
def multiple_raw_articles():
    """Multiple sample RawArticles from different sources."""
    from src.curator.models import RawArticle, ContentType
    return [
        RawArticle(
            title="GPT-5 Released",
            url="https://openai.com/blog/gpt-5",
            description="OpenAI releases GPT-5 with breakthrough capabilities.",
            source="rss_techcrunch",
            content_type=ContentType.MODEL_RELEASE,
        ),
        RawArticle(
            title="GPT-5 Launched by OpenAI",
            url="https://techcrunch.com/2026/07/gpt-5-launch?utm_source=twitter",
            description="OpenAI launched GPT-5 today.",
            source="rss_量子位",
            content_type=ContentType.MODEL_RELEASE,
        ),
        RawArticle(
            title="New LangGraph Version",
            url="https://github.com/langchain-ai/langgraph/releases/tag/v0.4.0",
            description="LangGraph 0.4.0 adds checkpoint persistence.",
            source="framework_watch",
            content_type=ContentType.AGENT_FRAMEWORK,
        ),
    ]


@pytest.fixture
def mock_llm_response():
    """Mock LLM curation response."""
    return [
        {
            "id": 1,
            "chinese_title": "OpenAI 发布 GPT-5",
            "chinese_summary": "GPT-5 在推理和代码能力上有重大突破，支持多模态输入。",
            "content_type": "model_release",
            "categories": ["LLM", "Industry"],
            "importance_score": 5,
            "recommendation_reason": "这是今年最重要的模型发布，直接影响你的 API 选择",
            "install_command": None,
            "has_price_change": False,
        },
        {
            "id": 2,
            "chinese_title": "LangGraph 0.4.0 发布",
            "chinese_summary": "新增持久化检查点功能，支持长时间运行的 Agent 工作流。",
            "content_type": "agent_framework",
            "categories": ["AI Agents", "Developer Tools"],
            "importance_score": 4,
            "recommendation_reason": "如果你在用 LangGraph，建议尽快升级",
            "install_command": "pip install langgraph --upgrade",
            "has_price_change": False,
        },
    ]


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure test env doesn't have real API keys."""
    # Save original values
    original = {}
    keys_to_clear = [
        "LLM_API_KEY", "SMTP_PASSWORD", "PH_DEV_TOKEN", "GITHUB_TOKEN"
    ]
    for key in keys_to_clear:
        if key in os.environ:
            original[key] = os.environ[key]
            del os.environ[key]
        else:
            original[key] = None

    yield

    # Restore
    for key, value in original.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]
