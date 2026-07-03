"""
LLM batch curation processor.

The core curation pipeline: takes deduplicated RawArticles,
sends them in batches to LLM for processing, and returns
CuratedArticles with Chinese summaries, scoring, and recommendations.
"""

import json
import logging
from datetime import datetime
from typing import Any

from src.aggregator.base import canonicalize_url
from src.curator.llm_client import LLMClient
from src.curator.models import (
    SORTING_BONUS,
    BatchCurationResult,
    ContentType,
    CuratedArticle,
    RawArticle,
)

logger = logging.getLogger(__name__)


class CurationProcessor:
    """Processes raw articles through LLM curation in batches."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        batch_prompt_template: str,
        content_type_guide: str,
        importance_guide: str,
        batch_size: int = 8,
    ):
        self.llm = llm_client
        self.system_prompt = system_prompt
        self.batch_prompt_template = batch_prompt_template
        self.content_type_guide = content_type_guide
        self.importance_guide = importance_guide
        self.batch_size = batch_size

        self.total_tokens_used = 0
        self.total_cost_rmb = 0.0

        # Estimated costs (DeepSeek V3 pricing as of 2026)
        self.INPUT_PRICE_PER_1K = 0.00027   # ¥ per 1K input tokens
        self.OUTPUT_PRICE_PER_1K = 0.0011   # ¥ per 1K output tokens

    def _build_content_type_list(self) -> str:
        """Build a formatted list of content types for the prompt."""
        types = [
            "- mcp_server: MCP 服务器发布/评测/教程",
            "- claude_skill: Claude Code 技能/插件",
            "- coding_tool: AI 编程工具更新（Claude Code/Cursor/Copilot）",
            "- agent_framework: Agent 开发框架版本更新",
            "- dev_tool: 通用 AI 开发工具",
            "- model_release: 商业模型 API 发布/定价变化",
            "- open_source_model: 开源模型权重发布",
            "- guide: 官方方法论/最佳实践指南",
            "- research: 学术论文/深度技术博客",
            "- industry: 行业新闻/商业分析/融资",
        ]
        return "\n".join(types)

    def _format_articles_for_prompt(self, articles: list[RawArticle]) -> str:
        """Format a batch of articles as JSON for the LLM prompt."""
        formatted = []
        for i, article in enumerate(articles, 1):
            formatted.append({
                "id": i,
                "title": article.title,
                "description": (article.description or "")[:300],
                "source": article.source,
                "original_content_type": article.content_type.value,
            })

        return json.dumps(formatted, ensure_ascii=False, indent=2)

    def _apply_sorting_bonus(self, article: CuratedArticle) -> CuratedArticle:
        """Apply sorting bonus to importance score based on content type."""
        bonus = SORTING_BONUS.get(article.content_type, 0)
        article.weighted_score = article.importance_score + bonus
        return article

    def _parse_llm_response(
        self, response: dict[str, Any], articles: list[RawArticle]
    ) -> list[CuratedArticle]:
        """Parse LLM JSON response into CuratedArticle objects."""
        curated: list[CuratedArticle] = []

        # Handle both single object and array responses
        items = response if isinstance(response, list) else response.get("articles", [response])

        for item in items:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id", -1)
            # Map back to original article (1-indexed)
            if isinstance(item_id, int) and 1 <= item_id <= len(articles):
                original = articles[item_id - 1]
            else:
                # Try to match by title if id is broken
                logger.debug("LLM response has no valid id, skipping")
                continue

            # Map content type string to enum
            ct_str = item.get("content_type", original.content_type.value)
            try:
                content_type = ContentType(ct_str)
            except ValueError:
                content_type = original.content_type

            # Extract install command
            install_cmd = item.get("install_command")
            if install_cmd and install_cmd in ("null", "None", None, ""):
                install_cmd = None

            curated_article = CuratedArticle(
                original=original,
                chinese_title=item.get("chinese_title", original.title),
                chinese_summary=item.get("chinese_summary", ""),
                content_type=content_type,
                categories=item.get("categories", []),
                importance_score=max(1, min(5, int(item.get("importance_score", 3)))),
                recommendation_reason=item.get("recommendation_reason", ""),
                install_command=install_cmd,
                has_price_change=item.get("has_price_change", False),
                curation_time=datetime.now(),
                llm_model_used=self.llm.model,
            )

            # Apply pricing change bonus
            if curated_article.has_price_change:
                curated_article.importance_score = min(5, curated_article.importance_score + 1)

            # Apply sorting bonus
            curated_article = self._apply_sorting_bonus(curated_article)

            curated.append(curated_article)

        return curated

    async def curate_batch(
        self, articles: list[RawArticle], batch_id: int
    ) -> BatchCurationResult:
        """
        Curate a single batch of articles through the LLM.

        Args:
            articles: Batch of RawArticles (1 to self.batch_size)
            batch_id: Sequential batch identifier

        Returns:
            BatchCurationResult with curated articles
        """
        if not articles:
            return BatchCurationResult(articles=[], batch_id=batch_id)

        # Build prompt
        articles_json = self._format_articles_for_prompt(articles)
        content_types = self._build_content_type_list()

        user_prompt = self.batch_prompt_template.format(
            count=len(articles),
            content_types=content_types,
            category_list="LLM, Computer Vision, NLP, Multimodal, Robotics, AI Safety, "
                          "AI Agents, AI Infrastructure, AI Applications, Research, "
                          "Industry, Developer Tools, Open Source",
            articles_json=articles_json,
        )

        try:
            # Call LLM
            response = await self.llm.chat_completion_with_json(
                system=self.system_prompt,
                user=user_prompt,
            )

            # Parse response
            curated = self._parse_llm_response(response, articles)

            # Estimate tokens and cost
            # Rough estimate: 4 chars per token for Chinese, 3 chars for code
            input_chars = len(self.system_prompt) + len(user_prompt)
            estimated_input_tokens = input_chars / 3.5
            estimated_output_tokens = len(json.dumps(response, ensure_ascii=False)) / 3.0

            tokens_used = int(estimated_input_tokens + estimated_output_tokens)
            cost = (
                estimated_input_tokens / 1000 * self.INPUT_PRICE_PER_1K
                + estimated_output_tokens / 1000 * self.OUTPUT_PRICE_PER_1K
            )

            self.total_tokens_used += tokens_used
            self.total_cost_rmb += cost

            logger.info(
                f"Batch {batch_id}: {len(curated)}/{len(articles)} curated, "
                f"~{tokens_used} tokens, ¥{cost:.4f}"
            )

            return BatchCurationResult(
                articles=curated,
                batch_id=batch_id,
                tokens_used=tokens_used,
                cost_estimate_rmb=round(cost, 4),
                success=True,
            )

        except Exception as e:
            logger.error(f"Batch {batch_id} curation failed: {e}")
            return BatchCurationResult(
                articles=[],
                batch_id=batch_id,
                success=False,
                error_message=str(e),
            )

    async def curate_all(
        self, articles: list[RawArticle]
    ) -> list[CuratedArticle]:
        """
        Curate all articles through LLM in batches.

        Articles are sorted by source priority (core first) before batching
        to ensure important sources are processed in earlier batches.
        """
        if not articles:
            return []

        # Sort: core priority first, then degraded
        from src.curator.models import SourcePriority

        def priority_order(a: RawArticle) -> int:
            order = {SourcePriority.CORE: 0, SourcePriority.DEGRADED: 1, SourcePriority.AUXILIARY: 2}
            return order.get(a.priority, 0)

        articles.sort(key=priority_order)

        # Batch articles
        batches: list[list[RawArticle]] = []
        for i in range(0, len(articles), self.batch_size):
            batches.append(articles[i : i + self.batch_size])

        logger.info(
            f"Curating {len(articles)} articles in {len(batches)} batches "
            f"(batch_size={self.batch_size})"
        )

        # Process batches sequentially to respect rate limits
        all_curated: list[CuratedArticle] = []
        failed_batches = 0

        for idx, batch in enumerate(batches):
            result = await self.curate_batch(batch, idx + 1)
            if result.success:
                all_curated.extend(result.articles)
            else:
                failed_batches += 1
                # Retry once with a smaller batch if possible
                if len(batch) > 1:
                    logger.warning(f"Retrying batch {idx + 1} with half size...")
                    for sub_batch in self._split_batch(batch):
                        retry_result = await self.curate_batch(sub_batch, idx * 100 + len(all_curated))
                        if retry_result.success:
                            all_curated.extend(retry_result.articles)
                        else:
                            failed_batches += 1

        logger.info(
            f"Curation complete: {len(all_curated)} curated from {len(articles)} articles. "
            f"Failed batches: {failed_batches}. "
            f"Total tokens: ~{self.total_tokens_used}, "
            f"Total cost: ¥{self.total_cost_rmb:.4f}"
        )

        return all_curated

    def _split_batch(self, batch: list[RawArticle]) -> list[list[RawArticle]]:
        """Split a batch into smaller sub-batches for retry."""
        half = max(1, len(batch) // 2)
        return [batch[:half], batch[half:]] if half < len(batch) else [batch]
