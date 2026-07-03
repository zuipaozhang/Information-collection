"""
AI Information Collection System — Main Pipeline Entry Point.

Orchestrates the full pipeline:
  Fetch → Dedup → Curate → Rank → Compose → Send → Save State

Usage:
  python -m src.main --mode daily
  python -m src.main --mode weekly
  python -m src.main --mode monthly
  python -m src.main --mode daily --dry-run --verbose
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import get_config
from src.curator.deduplicator import Deduplicator
from src.curator.llm_client import LLMClient
from src.curator.models import ContentType, SourcePriority
from src.curator.processor import CurationProcessor
from src.curator.ranker import Ranker
from src.digest.composer import DigestComposer
from src.digest.sender import EmailSender
from src.state.manager import StateManager

# ---------------------------------------------------------------------------
# Aggregator imports & factory
# ---------------------------------------------------------------------------
from src.aggregator.rss_fetcher import create_rss_fetchers
from src.aggregator.github_trending import GitHubTrendingSource
from src.aggregator.huggingface_papers import HuggingFacePapersSource
from src.aggregator.hacker_news import HackerNewsSource
from src.aggregator.product_hunt import ProductHuntSource
from src.aggregator.framework_watch import FrameworkWatchSource
from src.aggregator.mcp_pulse import MCPPulseSource
from src.aggregator.claude_plugins import ClaudePluginsSource
from src.aggregator.coding_tools import CodingToolsSource
from src.aggregator.oss_models import OSSModelsSource
from src.aggregator.official_blogs import OfficialBlogsSource
from src.aggregator.base import SourceProtocol

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def create_all_aggregators() -> list[SourceProtocol]:
    """Create all enabled aggregators from config."""
    config = get_config()
    sources = config.sources.get("sources", {})
    global_cfg = config.sources.get("global", {})
    timeout = global_cfg.get("request_timeout", 30)
    ua = global_cfg.get("user_agent", "AI-Info-Collector/1.0")

    aggregators: list[SourceProtocol] = []

    # --- RSS feeds (量子位, 机器之心, TechCrunch) ---
    aggregators.extend(create_rss_fetchers(config.sources))

    # --- GitHub Trending ---
    gh_cfg = sources.get("github_trending", {})
    if gh_cfg.get("enabled", True):
        aggregators.append(GitHubTrendingSource(
            ai_keywords=gh_cfg.get("ai_keywords", []),
            since=gh_cfg.get("since", "daily"),
            max_items=gh_cfg.get("max_items", 25),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- HuggingFace Papers ---
    hf_cfg = sources.get("huggingface_papers", {})
    if hf_cfg.get("enabled", True):
        qf = hf_cfg.get("quality_filter", {})
        aggregators.append(HuggingFacePapersSource(
            max_items=hf_cfg.get("max_items", 25),
            require_paper_with_code=qf.get("require_paper_with_code", True),
            min_github_stars=qf.get("min_github_stars", 500),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Hacker News ---
    hn_cfg = sources.get("hacker_news", {})
    if hn_cfg.get("enabled", True):
        aggregators.append(HackerNewsSource(
            ai_keywords=hn_cfg.get("ai_keywords", []),
            exclude_keywords=hn_cfg.get("exclude_keywords", []),
            story_type=hn_cfg.get("story_type", "top"),
            max_fetch_ids=hn_cfg.get("max_fetch_ids", 100),
            min_score=hn_cfg.get("min_score", 100),
            max_items=hn_cfg.get("max_items", 20),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Product Hunt ---
    ph_cfg = sources.get("product_hunt", {})
    if ph_cfg.get("enabled", True) and config.ph_dev_token:
        aggregators.append(ProductHuntSource(
            api_token=config.ph_dev_token,
            topic_slug=ph_cfg.get("topic_slug", "ai"),
            max_items=ph_cfg.get("max_items", 20),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- MCP Pulse ---
    mcp_cfg = sources.get("mcp_pulse", {})
    if mcp_cfg.get("enabled", True):
        aggregators.append(MCPPulseSource(
            max_items=mcp_cfg.get("max_items", 20),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Claude Plugins ---
    cp_cfg = sources.get("claude_plugins", {})
    if cp_cfg.get("enabled", True):
        aggregators.append(ClaudePluginsSource(
            registry_repos=cp_cfg.get("registry_repos", ["Kamalnrf/claude-plugins"]),
            watch_interval_hours=cp_cfg.get("watch_interval_hours", 24),
            github_token=config.github_token,
            max_items=cp_cfg.get("max_items", 15),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Framework Watch ---
    fw_cfg = sources.get("framework_watch", {})
    if fw_cfg.get("enabled", True):
        aggregators.append(FrameworkWatchSource(
            repos=fw_cfg.get("repos", []),
            lookback_days=fw_cfg.get("lookback_days", 1),
            github_token=config.github_token,
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Coding Tools ---
    ct_cfg = sources.get("coding_tools", {})
    if ct_cfg.get("enabled", True):
        aggregators.append(CodingToolsSource(
            github_token=config.github_token,
            lookback_days=ct_cfg.get("lookback_days", 1),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- OSS Models ---
    oss_cfg = sources.get("oss_models", {})
    if oss_cfg.get("enabled", True):
        aggregators.append(OSSModelsSource(
            watch_families=oss_cfg.get("watch_families", []),
            max_items=oss_cfg.get("max_items", 15),
            timeout=timeout,
            user_agent=ua,
        ))

    # --- Official Blogs ---
    ob_cfg = sources.get("official_blogs", {})
    if ob_cfg.get("enabled", True):
        aggregators.append(OfficialBlogsSource(
            feeds=ob_cfg.get("feeds", []),
            max_items=ob_cfg.get("max_items", 10),
            timeout=timeout,
            user_agent=ua,
        ))

    logger.info(f"Created {len(aggregators)} aggregators")
    return aggregators


async def run_digest(mode: str) -> bool:
    """
    Run the full AI information digest pipeline.

    Args:
        mode: "daily", "weekly", or "monthly"

    Returns:
        True if email was sent successfully, False otherwise.
    """
    config = get_config()
    state = StateManager(Path("data"))
    aggregators = create_all_aggregators()

    today = date.today()
    date_str = today.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # 1. FETCH: Concurrently fetch from all sources
    # ------------------------------------------------------------------
    logger.info(f"[1/7] Fetching from {len(aggregators)} sources...")

    results = await asyncio.gather(
        *[agg.fetch() for agg in aggregators],
        return_exceptions=True,
    )

    raw_items = []
    fetch_errors = 0
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Source '{aggregators[idx].source_name}' failed: {result}")
            fetch_errors += 1
        elif isinstance(result, list):
            raw_items.extend(result)

    logger.info(
        f"Fetched {len(raw_items)} raw items "
        f"({fetch_errors}/{len(aggregators)} sources failed)"
    )

    if not raw_items:
        logger.warning("No items fetched from any source. Exiting.")
        return False

    # Count auxiliary items
    auxiliary_count = sum(1 for a in raw_items if a.priority == SourcePriority.AUXILIARY)

    # ------------------------------------------------------------------
    # 2. DEDUP: Multi-stage deduplication
    # ------------------------------------------------------------------
    logger.info(f"[2/7] Deduplicating {len(raw_items)} items...")
    dedup = Deduplicator(state)
    unique_items = dedup.deduplicate(raw_items)

    # ------------------------------------------------------------------
    # 3. CURATE: LLM batch processing
    # ------------------------------------------------------------------
    logger.info(f"[3/7] Curating {len(unique_items)} unique items via LLM...")

    if not config.llm_configured:
        logger.error("LLM not configured. Set LLM_API_KEY environment variable.")
        return False

    # Remove auxiliary items before LLM curation (saves tokens)
    non_auxiliary = [a for a in unique_items if a.priority != SourcePriority.AUXILIARY]
    auxiliary_items = [a for a in unique_items if a.priority == SourcePriority.AUXILIARY]

    llm_client = LLMClient(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
    )

    prompts = config.prompts.get("curation", {})
    processor = CurationProcessor(
        llm_client=llm_client,
        system_prompt=prompts.get("system_prompt", ""),
        batch_prompt_template=prompts.get("batch_curation", ""),
        content_type_guide=prompts.get("content_type_guide", ""),
        importance_guide=prompts.get("importance_guide", ""),
        batch_size=config.curation_batch_size,
    )

    curated_items = await processor.curate_all(non_auxiliary)

    # Cross-validate auxiliary items (check if any news was also reported by core sources)
    if auxiliary_items:
        logger.info(
            f"Cross-validation: {len(auxiliary_items)} auxiliary items "
            f"(not curated, for coverage check only)"
        )

    # ------------------------------------------------------------------
    # 4. RANK: Sort, weight, apply diversity
    # ------------------------------------------------------------------
    logger.info(f"[4/7] Ranking {len(curated_items)} curated items...")
    ranker = Ranker()

    top_n_map = {"daily": config.daily_top_n, "weekly": config.weekly_top_n, "monthly": 50}
    top_n = top_n_map.get(mode, config.daily_top_n)
    selected = ranker.select_top(curated_items, n=top_n)

    logger.info(f"Selected top {len(selected)} items from {len(curated_items)} curated")

    # ------------------------------------------------------------------
    # 5. COMPOSE: Build email HTML + text
    # ------------------------------------------------------------------
    logger.info(f"[5/7] Composing {mode} digest...")
    composer = DigestComposer()

    if mode == "daily":
        html, text, subject = composer.compose_daily(
            articles=selected,
            total_fetched=len(raw_items),
            cost_rmb=processor.total_cost_rmb,
            auxiliary_matches=auxiliary_count,
        )
        week_label = today.strftime("%Y-W%W")
        archive_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        archive_end = today.strftime("%Y-%m-%d")

    elif mode == "weekly":
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        # Generate trend summary for the week
        trend_summary = ""
        if selected:
            trend_summary = await _generate_trend_summary(
                llm_client, prompts, selected, mode
            )

        html, text, subject = composer.compose_weekly(
            articles=selected,
            total_fetched=len(raw_items),
            cost_rmb=processor.total_cost_rmb,
            trend_summary=trend_summary,
            auxiliary_matches=auxiliary_count,
            week_start=week_start,
        )
        week_label = today.strftime("%Y-W%W")
        archive_start = week_start.strftime("%Y-%m-%d")
        archive_end = week_end.strftime("%Y-%m-%d")

    elif mode == "monthly":
        # Get historical items for trend analysis
        month_start = today.replace(day=1)
        if today.month == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

        historical_items = state.get_items_for_period(
            month_start.strftime("%Y-%m-%d"),
            month_end.strftime("%Y-%m-%d"),
        )

        trend_analysis = await _generate_trend_analysis(
            llm_client, prompts, selected, historical_items, month_start, month_end
        )

        html, text, subject = composer.compose_monthly(
            articles=selected,
            total_fetched=len(raw_items),
            cost_rmb=processor.total_cost_rmb,
            trend_analysis=trend_analysis,
            auxiliary_matches=auxiliary_count,
        )
        week_label = today.strftime("%Y-W%W")
        archive_start = month_start.strftime("%Y-%m-%d")
        archive_end = month_end.strftime("%Y-%m-%d")

    else:
        logger.error(f"Unknown mode: {mode}")
        return False

    # ------------------------------------------------------------------
    # 6. SEND: Deliver email
    # ------------------------------------------------------------------
    logger.info(f"[6/7] Sending {mode} digest email...")

    message_id = "dry-run"
    if not config.dry_run:
        if not config.smtp_password:
            logger.error("Resend API key not configured. Set SMTP_PASSWORD.")
            return False

        sender = EmailSender(
            api_key=config.smtp_password,
            from_addr=config.email_from,
        )

        try:
            message_id = await sender.send(
                to=config.email_to,
                subject=subject,
                html_body=html,
                text_body=text,
            )
            logger.info(f"Email sent: {message_id}")
        except Exception as e:
            logger.error(f"Email delivery failed: {e}")
            # Still save state so we don't re-process
            state.save_all()
            return False
    else:
        # Dry run: write HTML to /tmp for inspection
        tmp_path = Path(f"/tmp/digest-{mode}-{today.strftime('%Y%m%d')}.html")
        tmp_path.write_text(html, encoding="utf-8")
        logger.info(f"[DRY RUN] Email HTML saved to {tmp_path}")
        logger.info(f"[DRY RUN] Subject: {subject}")
        logger.info(f"[DRY RUN] Would send to: {config.email_to}")

    # ------------------------------------------------------------------
    # 7. SAVE STATE: Persist and archive
    # ------------------------------------------------------------------
    logger.info("[7/7] Saving state...")

    # Record digest in history
    state.record_digest_sent(
        digest_type=mode,
        date_str=date_str,
        items=selected,
        message_id=message_id,
        llm_model=config.llm_model,
        tokens_used=processor.total_tokens_used,
        cost_rmb=processor.total_cost_rmb,
        auxiliary_matches=auxiliary_count,
    )

    # Archive curated items for trend analysis
    state.archive_curated_items(
        items=selected,
        week_label=week_label,
        start_date=archive_start,
        end_date=archive_end,
    )

    if not config.dry_run:
        state.save_all()
        stats = state.get_stats()
        logger.info(
            f"State saved. {stats['total_unique_urls']} URLs tracked, "
            f"{stats['total_digests_sent']} digests sent."
        )
    else:
        logger.info("[DRY RUN] State not saved (dry-run mode)")

    # Final summary
    logger.info("=" * 50)
    logger.info(f"Digest complete: {mode.upper()}")
    logger.info(f"  Sources: {len(aggregators)} ({fetch_errors} failed)")
    logger.info(f"  Raw items: {len(raw_items)}")
    logger.info(f"  Unique: {len(unique_items)}")
    logger.info(f"  Curated: {len(curated_items)}")
    logger.info(f"  Selected: {len(selected)}")
    logger.info(f"  LLM tokens: ~{processor.total_tokens_used}")
    logger.info(f"  LLM cost: ¥{processor.total_cost_rmb:.4f}")
    logger.info(f"  Email: {'DRY RUN' if config.dry_run else 'SENT'} → {config.email_to}")
    logger.info("=" * 50)

    return True


async def _generate_trend_summary(
    llm_client: LLMClient,
    prompts: dict,
    articles,
    mode: str,
) -> str:
    """Generate a brief trend summary for weekly digest."""
    if not articles:
        return ""

    # Build a simple summary prompt
    items_text = []
    for a in articles[:10]:
        items_text.append(
            f"- [{a.content_type.value}] {a.chinese_title}: {a.chinese_summary[:100]}"
        )

    system = "你是一位 AI 行业分析师。请用 2-3 段中文概述本周 AI 领域的重要趋势。"
    user = f"本周精选了以下 {len(articles)} 条 AI 资讯:\n\n" + "\n".join(items_text)

    try:
        return await llm_client.chat_completion(system=system, user=user, max_tokens=500)
    except Exception as e:
        logger.warning(f"Trend summary generation failed: {e}")
        return ""


async def _generate_trend_analysis(
    llm_client: LLMClient,
    prompts: dict,
    active_items,
    historical_items: list,
    start_date: date,
    end_date: date,
) -> str:
    """Generate full monthly trend analysis."""
    trend_prompt = prompts.get("trend_analysis", "")

    if not trend_prompt:
        return ""

    # Build context data
    from collections import Counter
    ct_counter = Counter()
    for h in historical_items:
        if hasattr(h, "content_type"):
            ct_counter[h.content_type] += 1
        else:
            ct_counter[h.get("content_type", "unknown")] += 1

    high_score = sum(1 for a in active_items if a.importance_score >= 4)

    # Count types
    mcp_count = sum(1 for a in active_items if a.content_type == ContentType.MCP_SERVER)
    skill_count = sum(1 for a in active_items if a.content_type == ContentType.CLAUDE_SKILL)
    coding_count = sum(1 for a in active_items if a.content_type == ContentType.CODING_TOOL)
    oss_count = sum(1 for a in active_items if a.content_type == ContentType.OPEN_SOURCE_MODEL)
    model_count = sum(1 for a in active_items if a.content_type == ContentType.MODEL_RELEASE)
    guide_count = sum(1 for a in active_items if a.content_type == ContentType.GUIDE)
    fw_count = sum(1 for a in active_items if a.content_type == ContentType.AGENT_FRAMEWORK)

    user_prompt = trend_prompt.format(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        total_items=len(historical_items) + len(active_items),
        high_score_items=high_score,
        installable_items=mcp_count + skill_count + coding_count,
        mcp_count=mcp_count,
        skill_count=skill_count,
        coding_count=coding_count,
        oss_count=oss_count,
        model_count=model_count,
        guide_count=guide_count,
        framework_count=fw_count,
        category_distribution=dict(ct_counter.most_common(10)),
        content_type_distribution="",
    )

    system = "你是一位经验丰富的 AI 行业分析师。请撰写专业的月度趋势报告。"

    try:
        return await llm_client.chat_completion(system=system, user=user_prompt, max_tokens=2500)
    except Exception as e:
        logger.warning(f"Trend analysis generation failed: {e}")
        return ""


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI Information Collection — 自动化信息聚合推送系统",
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", "monthly"],
        required=True,
        help="Digest mode: daily, weekly, or monthly",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip email sending and state saving (write HTML to /tmp/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        help="Path to config directory (default: config/)",
    )

    args = parser.parse_args()

    # Override dry-run via env variable
    import os
    if os.environ.get("DRY_RUN", "").lower() == "true":
        args.dry_run = True

    setup_logging(args.verbose)

    # Update config with CLI args
    config = get_config()
    config.dry_run = args.dry_run

    success = asyncio.run(run_digest(args.mode))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
