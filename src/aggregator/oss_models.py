"""
Open-source model release watcher.

Monitors HuggingFace Models trending and Ollama library for new
open-source model weight releases (Qwen, Llama, DeepSeek, Mistral, etc.).
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from src.aggregator.base import (
    SourceProtocol,
    canonicalize_url,
    create_http_client,
)
from src.curator.models import ContentType, RawArticle

logger = logging.getLogger(__name__)

HF_API_URL = "https://huggingface.co/api"


class OSSModelsSource(SourceProtocol):
    """Monitors open-source model releases."""

    def __init__(
        self,
        watch_families: list[str],
        max_items: int = 15,
        timeout: int = 30,
        user_agent: str = "AI-Info-Collector/1.0",
    ):
        self.watch_families = [f.lower() for f in watch_families]
        self.max_items = max_items
        self.timeout = timeout
        self.user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "oss_models"

    @property
    def default_content_type(self) -> ContentType:
        return ContentType.OPEN_SOURCE_MODEL

    def _is_watched_family(self, model_name: str) -> bool:
        """Check if model belongs to a watched family."""
        name_lower = model_name.lower()
        return any(family.lower() in name_lower for family in self.watch_families)

    async def _fetch_hf_trending_models(
        self, client: httpx.AsyncClient
    ) -> list[RawArticle]:
        """Fetch trending models from HuggingFace."""
        articles: list[RawArticle] = []
        try:
            url = f"{HF_API_URL}/models"
            params = {"sort": "trendingScore", "limit": 50, "full": "false"}
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"HF Models API returned {response.status_code}")
                return articles

            models = response.json()
            for model in models[:50]:
                if not isinstance(model, dict):
                    continue

                model_id = model.get("id", "")
                if not self._is_watched_family(model_id):
                    continue

                # Model metadata
                downloads = model.get("downloads", 0)
                likes = model.get("likes", 0)
                pipeline_tag = model.get("pipeline_tag", "")

                # Description
                description = model.get("description", "")
                if not description:
                    description = f"Trending OSS model: {model_id}. Downloads: {downloads}, Likes: {likes}"

                # Build URL
                model_url = f"https://huggingface.co/{model_id}"

                # Parse last modified
                published_at = None
                last_modified = model.get("lastModified", "")
                if last_modified:
                    try:
                        published_at = datetime.fromisoformat(
                            last_modified.replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

                # Determine install command
                install_cmd = f"ollama pull {model_id.split('/')[-1].lower()}"

                articles.append(RawArticle(
                    title=f"🤗 {model_id}",
                    url=canonicalize_url(model_url),
                    description=description[:500],
                    source=self.source_name,
                    content_type=ContentType.OPEN_SOURCE_MODEL,
                    published_at=published_at,
                    metadata={
                        "model_id": model_id,
                        "downloads": downloads,
                        "likes": likes,
                        "pipeline_tag": pipeline_tag,
                        "install_command": install_cmd,
                        "source": "huggingface_trending",
                    },
                ))

                if len(articles) >= self.max_items:
                    break
        except Exception as e:
            logger.error(f"HF Models trending fetch failed: {e}")

        return articles

    async def _fetch_ollama_library(
        self, client: httpx.AsyncClient
    ) -> list[RawArticle]:
        """
        Check Ollama library for recently updated models.

        Note: Ollama doesn't have a public RSS. We use the search API
        to find recent additions matching watched families.
        """
        # Ollama doesn't provide a good API for detecting new models.
        # We primarily rely on HF Trending for model discovery.
        # This is a placeholder for future Ollama API integration.
        return []

    async def fetch(self) -> list[RawArticle]:
        """Fetch trending open-source models."""
        async with create_http_client(self.timeout, self.user_agent) as client:
            hf_models = await self._fetch_hf_trending_models(client)
            # ollama = await self._fetch_ollama_library(client)

        articles = hf_models  # + ollama
        logger.info(
            f"OSS Models: found {len(articles)} models from watched families: "
            f"{', '.join(self.watch_families)}"
        )
        return articles
