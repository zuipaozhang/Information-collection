"""
Digest composer.

Assembles curated articles into HTML email digests using Jinja2 templates.
Generates both HTML and plain text versions for MIME multipart emails.
"""

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.curator.models import (
    INSTALLABLE_TYPES,
    ContentType,
    CuratedArticle,
)

logger = logging.getLogger(__name__)

# Content type display labels in Chinese
CONTENT_TYPE_LABELS = {
    ContentType.MCP_SERVER: "MCP 服务器",
    ContentType.CLAUDE_SKILL: "Claude 技能",
    ContentType.CODING_TOOL: "编程工具",
    ContentType.AGENT_FRAMEWORK: "Agent 框架",
    ContentType.DEV_TOOL: "开发工具",
    ContentType.MODEL_RELEASE: "模型发布",
    ContentType.OPEN_SOURCE_MODEL: "开源模型",
    ContentType.GUIDE: "方法指南",
    ContentType.RESEARCH: "研究论文",
    ContentType.INDUSTRY: "行业动态",
}

# Source display labels
SOURCE_LABELS: dict[str, str] = {
    "github_trending": "GitHub Trending",
    "huggingface_papers": "HuggingFace Papers",
    "rss_量子位": "量子位",
    "rss_机器之心": "机器之心",
    "hacker_news": "Hacker News",
    "product_hunt": "Product Hunt",
    "mcp_pulse": "PulseMCP",
    "claude_plugins": "Claude 插件",
    "framework_watch": "框架更新",
    "coding_tools": "编程工具",
    "oss_models": "开源模型",
    "official_blogs": "官方博客",
}

# Tech content types (non-installable)
TECH_TYPES = {
    ContentType.AGENT_FRAMEWORK,
    ContentType.DEV_TOOL,
    ContentType.MODEL_RELEASE,
    ContentType.OPEN_SOURCE_MODEL,
    ContentType.GUIDE,
    ContentType.RESEARCH,
    ContentType.INDUSTRY,
}


class DigestComposer:
    """Composes email digests from curated articles."""

    def __init__(self, templates_dir: str | Path = ""):
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            self.templates_dir = Path(__file__).parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
        )

    def _item_to_template_data(self, item: CuratedArticle) -> dict[str, Any]:
        """Convert a CuratedArticle to template-friendly data."""
        url = item.original.url
        source_label = SOURCE_LABELS.get(item.original.source, item.original.source)
        ct_label = CONTENT_TYPE_LABELS.get(item.content_type, item.content_type.value)

        return {
            "chinese_title": item.chinese_title,
            "chinese_summary": item.chinese_summary,
            "content_type": item.content_type.value,
            "content_type_label": ct_label,
            "categories": item.categories,
            "importance_score": item.importance_score,
            "weighted_score": item.weighted_score,
            "recommendation_reason": item.recommendation_reason,
            "install_command": item.install_command,
            "url": url,
            "source_label": source_label,
            "source": item.original.source,
        }

    def _compute_stats(
        self,
        items: list[CuratedArticle],
        total_fetched: int,
        cost_rmb: float,
        auxiliary_matches: int = 0,
    ) -> dict[str, Any]:
        """Compute statistics for the digest footer."""
        installable_count = sum(
            1 for a in items if a.content_type in INSTALLABLE_TYPES
        )
        framework_count = sum(
            1 for a in items if a.content_type == ContentType.AGENT_FRAMEWORK
        )
        tech_count = len(items) - installable_count - framework_count

        return {
            "total_fetched": total_fetched,
            "curated_count": len(items),
            "installable_count": installable_count,
            "framework_count": framework_count,
            "tech_count": tech_count,
            "cost_rmb": cost_rmb,
            "auxiliary_matches": auxiliary_matches,
        }

    def compose_daily(
        self,
        articles: list[CuratedArticle],
        total_fetched: int,
        cost_rmb: float,
        auxiliary_matches: int = 0,
        topic_date: date | None = None,
    ) -> tuple[str, str, str]:
        """
        Compose a daily digest email.

        Returns:
            (html_body, text_body, subject)
        """
        today = topic_date or date.today()
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

        template = self.env.get_template("daily.html")

        # Split articles into installable and tech
        items_data = [self._item_to_template_data(a) for a in articles]
        installable = [d for d in items_data if ContentType(d["content_type"]) in INSTALLABLE_TYPES]
        tech = [d for d in items_data if ContentType(d["content_type"]) in TECH_TYPES]

        subject = f"🤖 AI 信息日报 · {today.strftime('%Y.%m.%d')} 星期{weekday_names[today.weekday()]}"

        html = template.render(
            subject=subject,
            title_tag="AI INFORMATION DAILY",
            title=f"🤖 AI 信息日报",
            date_str=f"{today.year}年{today.month}月{today.day}日 星期{weekday_names[today.weekday()]}",
            installable=installable,
            tech_items=tech,
            stats=self._compute_stats(articles, total_fetched, cost_rmb, auxiliary_matches),
            unsubscribe_url="{{ unsubscribe_url }}",
        )

        text = self._html_to_text(html, subject)
        return html, text, subject

    def compose_weekly(
        self,
        articles: list[CuratedArticle],
        total_fetched: int,
        cost_rmb: float,
        trend_summary: str = "",
        auxiliary_matches: int = 0,
        week_start: date | None = None,
    ) -> tuple[str, str, str]:
        """Compose a weekly roundup email."""
        if week_start is None:
            week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)

        template = self.env.get_template("weekly.html")

        items_data = [self._item_to_template_data(a) for a in articles]
        installable = [d for d in items_data if ContentType(d["content_type"]) in INSTALLABLE_TYPES]
        tech = [d for d in items_data if ContentType(d["content_type"]) in TECH_TYPES]

        # Top 3 by importance
        top_rated = sorted(items_data, key=lambda d: d["weighted_score"], reverse=True)[:3]

        # Content type distribution
        ct_counter = Counter()
        for a in articles:
            ct_counter[CONTENT_TYPE_LABELS.get(a.content_type, a.content_type.value)] += 1

        subject = f"📊 AI 信息周报 · {week_start.strftime('%Y.%m.%d')} - {week_end.strftime('%m.%d')}"

        html = template.render(
            subject=subject,
            title_tag="AI INFORMATION WEEKLY",
            title=f"📊 AI 信息周报",
            date_str=f"{week_start.strftime('%Y.%m.%d')} — {week_end.strftime('%Y.%m.%d')}",
            trend_summary=trend_summary,
            installable=installable,
            top_rated=top_rated,
            tech_items=tech,
            content_type_distribution=dict(ct_counter.most_common()),
            total_items=len(articles),
            stats=self._compute_stats(articles, total_fetched, cost_rmb, auxiliary_matches),
            unsubscribe_url="{{ unsubscribe_url }}",
        )

        text = self._html_to_text(html, subject)
        return html, text, subject

    def compose_monthly(
        self,
        articles: list[CuratedArticle],
        total_fetched: int,
        cost_rmb: float,
        trend_analysis: str = "",
        auxiliary_matches: int = 0,
        month_date: date | None = None,
    ) -> tuple[str, str, str]:
        """Compose a monthly trend report email."""
        if month_date is None:
            month_date = date.today()

        template = self.env.get_template("monthly.html")

        items_data = [self._item_to_template_data(a) for a in articles]
        installable = [d for d in items_data if ContentType(d["content_type"]) in INSTALLABLE_TYPES]

        # Top 10
        top_rated = sorted(items_data, key=lambda d: d["weighted_score"], reverse=True)[:10]

        # Distribution
        ct_counter = Counter()
        for a in articles:
            ct_counter[CONTENT_TYPE_LABELS.get(a.content_type, a.content_type.value)] += 1

        # Average importance
        avg_imp = sum(a.importance_score for a in articles) / max(len(articles), 1)

        stats = self._compute_stats(articles, total_fetched, cost_rmb, auxiliary_matches)
        stats["avg_importance"] = avg_imp

        subject = f"📈 AI 月度趋势报告 · {month_date.year}年{month_date.month}月"

        html = template.render(
            subject=subject,
            title_tag="AI MONTHLY TRENDS",
            title=f"📈 AI 月度趋势报告",
            date_str=f"{month_date.year}年{month_date.month}月",
            month_label=f"{month_date.year}年{month_date.month}月",
            trend_analysis=trend_analysis,
            installable=installable,
            top_rated=top_rated,
            content_type_distribution=dict(ct_counter.most_common()),
            stats=stats,
            unsubscribe_url="{{ unsubscribe_url }}",
        )

        text = self._html_to_text(html, subject)
        return html, text, subject

    def _html_to_text(self, html: str, subject: str) -> str:
        """Generate a plain text fallback from HTML."""
        # Strip HTML tags
        clean = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", "", clean)
        clean = unescape(clean)

        # Collapse whitespace
        clean = re.sub(r"\n\s*\n+", "\n\n", clean)
        clean = clean.strip()

        # Add header
        return f"{subject}\n{'=' * len(subject)}\n\n{clean}"
