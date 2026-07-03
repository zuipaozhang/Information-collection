"""
Configuration loader.

Loads and validates YAML configuration files (sources.yaml, categories.yaml,
prompts.yaml) using Pydantic models. Environment variables override YAML values
for sensitive fields (API keys, SMTP credentials).
"""

import os
from pathlib import Path
from typing import Any

import yaml


# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML file from the config directory."""
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_sources_config() -> dict[str, Any]:
    """Load and return the sources configuration."""
    return _load_yaml("sources.yaml")


def load_categories_config() -> dict[str, Any]:
    """Load and return the categories configuration."""
    return _load_yaml("categories.yaml")


def load_prompts_config() -> dict[str, Any]:
    """Load and return the prompts configuration."""
    return _load_yaml("prompts.yaml")


class AppConfig:
    """
    Centralized application configuration.

    Loads from YAML config files and environment variables.
    Environment variables take precedence for secrets.
    """

    def __init__(self):
        # Load YAML configs
        self.sources = load_sources_config()
        self.categories = load_categories_config()
        self.prompts = load_prompts_config()

        # Global settings from sources.yaml
        global_cfg = self.sources.get("global", {})
        self.max_per_source: int = global_cfg.get("max_per_source", 30)
        self.request_timeout: int = global_cfg.get("request_timeout", 30)
        self.rate_limit_delay_ms: int = global_cfg.get("rate_limit_delay_ms", 500)
        self.user_agent: str = global_cfg.get(
            "user_agent", "AI-Info-Collector/1.0 (GitHub Actions; Digest Bot)"
        )

        # LLM settings (env overrides)
        self.llm_api_key: str = os.environ.get("LLM_API_KEY", "")
        self.llm_base_url: str = os.environ.get(
            "LLM_BASE_URL", "https://api.deepseek.com/v1"
        )
        self.llm_model: str = os.environ.get("LLM_MODEL", "deepseek-chat")

        # SMTP settings (env overrides)
        self.smtp_host: str = os.environ.get("SMTP_HOST", "smtp.resend.com")
        self.smtp_port: int = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_username: str = os.environ.get("SMTP_USERNAME", "")
        self.smtp_password: str = os.environ.get("SMTP_PASSWORD", "")

        # Email settings
        self.email_from: str = os.environ.get("EMAIL_FROM", "")
        self.email_to: str = os.environ.get("EMAIL_TO", "")

        # API tokens
        self.ph_dev_token: str = os.environ.get("PH_DEV_TOKEN", "")
        self.github_token: str = os.environ.get("GITHUB_TOKEN", "")

        # Digest settings
        self.daily_top_n: int = 8
        self.weekly_top_n: int = 18
        self.curation_batch_size: int = 8

        # Dry run
        self.dry_run: bool = os.environ.get("DRY_RUN", "false").lower() == "true"

    @property
    def llm_configured(self) -> bool:
        """Check if LLM credentials are configured."""
        return bool(self.llm_api_key)

    @property
    def smtp_configured(self) -> bool:
        """Check if SMTP credentials are configured."""
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)

    def get_enabled_sources(self) -> dict[str, Any]:
        """Return only enabled source configurations."""
        sources = self.sources.get("sources", {})
        enabled = {}
        for name, cfg in sources.items():
            if isinstance(cfg, dict) and cfg.get("enabled", True):
                enabled[name] = cfg
        return enabled

    def get_priority_sources(self, priority: str) -> dict[str, Any]:
        """Return sources filtered by priority tier."""
        sources = self.sources.get("sources", {})
        return {
            name: cfg
            for name, cfg in sources.items()
            if isinstance(cfg, dict)
            and cfg.get("enabled", True)
            and cfg.get("priority", "core") == priority
        }


# Singleton instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get or create the global AppConfig instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
