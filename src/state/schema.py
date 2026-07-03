"""
State file Pydantic schemas.

Defines the structure for seen_urls.json, digest_history.json,
and weekly archive files in curated_archive/.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SeenURLEntry(BaseModel):
    """A single entry in the seen_urls tracking table."""

    canonical_url: str
    first_seen: datetime
    last_seen: datetime
    source: str
    content_type: str
    times_seen: int = 1
    included_in: list[dict] = Field(default_factory=list)
    # Example: [{"digest_type": "daily", "digest_date": "2026-07-03"}]


class SeenURLStats(BaseModel):
    """Statistics for the seen_urls store."""

    total_unique_urls: int = 0
    last_pruned: datetime | None = None


class SeenURLStore(BaseModel):
    """The top-level seen_urls.json structure."""

    version: int = 1
    urls: dict[str, SeenURLEntry] = Field(default_factory=dict)
    stats: SeenURLStats = Field(default_factory=SeenURLStats)


class DigestRecord(BaseModel):
    """A single digest send record."""

    digest_type: str  # "daily" | "weekly" | "monthly"
    date: str         # "2026-07-03"
    items_count: int
    by_type: dict[str, int] = Field(default_factory=dict)
    auxiliary_matches: int = 0
    message_id: str
    sent_at: datetime
    llm_model: str
    tokens_used: int = 0
    cost_rmb: float = 0.0


class DigestHistory(BaseModel):
    """The top-level digest_history.json structure."""

    digests: list[DigestRecord] = Field(default_factory=list)


class SubscriptionPreferences(BaseModel):
    """User subscription preferences."""

    daily_enabled: bool = True
    weekly_enabled: bool = True
    monthly_enabled: bool = True
    email_to: str = ""


class ArchiveItem(BaseModel):
    """A single archived curated article."""

    title: str
    url: str
    source: str
    content_type: str
    chinese_title: str
    chinese_summary: str
    categories: list[str] = Field(default_factory=list)
    importance_score: int = 3
    weighted_score: float = 0.0
    recommendation_reason: str = ""
    install_command: str | None = None
    curation_date: str  # "2026-07-03"


class WeeklyArchive(BaseModel):
    """The structure of a curated_archive/2026-W27.json file."""

    week: str  # "2026-W27"
    start_date: str
    end_date: str
    items: list[ArchiveItem] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)
    content_type_counts: dict[str, int] = Field(default_factory=dict)
