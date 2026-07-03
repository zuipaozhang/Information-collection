"""
Data models for the curation pipeline.

Defines ContentType enum, RawArticle (input from aggregators),
and CuratedArticle (output from LLM curation).
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Content type classification for articles."""

    # === Directly usable tools (sorting bonus +1) ===
    MCP_SERVER = "mcp_server"           # MCP server
    CLAUDE_SKILL = "claude_skill"       # Claude Code skill/plugin
    CODING_TOOL = "coding_tool"         # AI coding tool updates (Claude Code/Cursor/Copilot)

    # === Tech selection reference ===
    AGENT_FRAMEWORK = "agent_framework" # Agent framework updates
    DEV_TOOL = "dev_tool"               # General AI dev tool
    MODEL_RELEASE = "model_release"     # Commercial model API release/pricing
    OPEN_SOURCE_MODEL = "open_source_model"  # Open-source model weight release

    # === Knowledge & trends ===
    GUIDE = "guide"                     # Official methodology/best-practice guide
    RESEARCH = "research"               # Paper/technical breakthrough (degraded priority)
    INDUSTRY = "industry"               # Industry news/business/funding


class SourcePriority(str, Enum):
    """Source priority tier."""
    CORE = "core"           # Full participation in ranking
    DEGRADED = "degraded"   # Extra quality filters applied
    AUXILIARY = "auxiliary" # Cross-validation only, excluded from push quota


# Sorting bonus rules: types that directly benefit the user
SORTING_BONUS: dict[ContentType, float] = {
    ContentType.MCP_SERVER: 1.0,
    ContentType.CLAUDE_SKILL: 1.0,
    ContentType.CODING_TOOL: 1.0,
    ContentType.OPEN_SOURCE_MODEL: 0.5,
}

# Types that should appear in email's "installable tools" section
INSTALLABLE_TYPES: set[ContentType] = {
    ContentType.MCP_SERVER,
    ContentType.CLAUDE_SKILL,
    ContentType.CODING_TOOL,
}


class RawArticle(BaseModel):
    """Normalized article from any data source, before curation."""

    title: str
    url: str
    description: str = ""
    source: str                              # e.g. "github_trending", "mcp_pulse"
    content_type: ContentType                # Initial classification from source
    priority: SourcePriority = SourcePriority.CORE
    auxiliary: bool = False                  # Auxiliary source flag
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # Source-specific extras
    fetch_time: datetime = Field(default_factory=datetime.now)


class CuratedArticle(BaseModel):
    """Article after LLM curation, ready for digest inclusion."""

    original: RawArticle
    chinese_title: str
    chinese_summary: str                     # 2-3 sentences in Chinese
    content_type: ContentType                # Confirmed/corrected by LLM
    categories: list[str] = Field(default_factory=list)  # 1-3 category tags
    importance_score: int = 3                # 1-5 raw score (before weighting)
    weighted_score: float = 0.0              # After applying sorting bonus
    recommendation_reason: str = ""          # One-sentence Chinese recommendation
    install_command: str | None = None       # Only for installable types
    has_price_change: bool = False           # Pricing change flag for model_release
    curation_time: datetime = Field(default_factory=datetime.now)
    llm_model_used: str = ""


class BatchCurationResult(BaseModel):
    """Result from a single LLM curation batch."""

    articles: list[CuratedArticle]
    batch_id: int
    tokens_used: int = 0
    cost_estimate_rmb: float = 0.0
    success: bool = True
    error_message: str = ""
