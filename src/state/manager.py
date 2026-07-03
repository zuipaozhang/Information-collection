"""
Persistent state manager.

Manages all on-disk state using JSON files in the data/ directory.
State is auto-committed to the git repo by GitHub Actions workflows.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.curator.models import CuratedArticle
from src.state.schema import (
    ArchiveItem,
    DigestHistory,
    DigestRecord,
    SeenURLEntry,
    SeenURLStats,
    SeenURLStore,
    WeeklyArchive,
)


class StateManager:
    """
    Manages persistent state across runs.

    State files:
     - data/seen_urls.json: Deduplication tracking
     - data/digest_history.json: History of all sent digests
     - data/curated_archive/YYYY-Www.json: Weekly archived curated items
    """

    # Pruning thresholds
    MAX_URLS = 10000       # Prune when exceeding this
    MAX_AGE_DAYS = 90      # Drop entries older than this

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "curated_archive").mkdir(parents=True, exist_ok=True)

        self.seen_urls_path = self.data_dir / "seen_urls.json"
        self.history_path = self.data_dir / "digest_history.json"
        self.archive_dir = self.data_dir / "curated_archive"

        # Lazy-loaded state
        self._seen_urls: SeenURLStore | None = None
        self._history: DigestHistory | None = None

    # ------------------------------------------------------------------
    # Seen URLs
    # ------------------------------------------------------------------

    def load_seen_urls(self) -> SeenURLStore:
        """Load seen_urls from disk, or return empty store."""
        if self._seen_urls is not None:
            return self._seen_urls

        if self.seen_urls_path.exists():
            try:
                with open(self.seen_urls_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._seen_urls = SeenURLStore(**data)
            except Exception:
                self._seen_urls = SeenURLStore()
        else:
            self._seen_urls = SeenURLStore()

        return self._seen_urls

    def is_seen(self, canonical_url: str) -> bool:
        """Check if a URL has already been processed."""
        store = self.load_seen_urls()
        return canonical_url in store.urls

    def get_seen_entry(self, canonical_url: str) -> SeenURLEntry | None:
        """Get the tracking entry for a URL, if it exists."""
        store = self.load_seen_urls()
        return store.urls.get(canonical_url)

    def mark_as_seen(
        self,
        canonical_url: str,
        source: str,
        content_type: str,
        first_seen: datetime | None = None,
    ) -> None:
        """Mark a URL as seen. Updates existing entry if already tracked."""
        store = self.load_seen_urls()
        now = first_seen or datetime.now()

        if canonical_url in store.urls:
            entry = store.urls[canonical_url]
            entry.last_seen = now
            entry.times_seen += 1
            if source not in entry.source.split(","):
                entry.source = f"{entry.source},{source}"
        else:
            store.urls[canonical_url] = SeenURLEntry(
                canonical_url=canonical_url,
                first_seen=now,
                last_seen=now,
                source=source,
                content_type=content_type,
                times_seen=1,
            )

        store.stats.total_unique_urls = len(store.urls)

    def mark_included_in_digest(
        self, canonical_url: str, digest_type: str, digest_date: str
    ) -> None:
        """Record that a URL was included in a sent digest."""
        store = self.load_seen_urls()
        entry = store.urls.get(canonical_url)
        if entry:
            entry.included_in.append({
                "digest_type": digest_type,
                "digest_date": digest_date,
            })

    def batch_mark_seen(
        self,
        urls: list[str],
        source: str,
        content_type: str = "unknown",
    ) -> None:
        """Mark multiple URLs as seen from the same source."""
        for url in urls:
            self.mark_as_seen(url, source, content_type)

    def prune_seen_urls(self, force: bool = False) -> int:
        """Remove old entries. Returns number of entries removed."""
        store = self.load_seen_urls()

        should_prune = force or store.stats.total_unique_urls > self.MAX_URLS
        if not should_prune:
            return 0

        cutoff = datetime.now() - timedelta(days=self.MAX_AGE_DAYS)
        removed = 0

        urls_to_delete = []
        for url, entry in store.urls.items():
            if entry.last_seen < cutoff:
                urls_to_delete.append(url)

        for url in urls_to_delete:
            del store.urls[url]
            removed += 1

        store.stats.total_unique_urls = len(store.urls)
        store.stats.last_pruned = datetime.now()

        return removed

    # ------------------------------------------------------------------
    # Digest History
    # ------------------------------------------------------------------

    def load_history(self) -> DigestHistory:
        """Load digest history from disk."""
        if self._history is not None:
            return self._history

        if self.history_path.exists():
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history = DigestHistory(**data)
            except Exception:
                self._history = DigestHistory()
        else:
            self._history = DigestHistory()

        return self._history

    def record_digest_sent(
        self,
        digest_type: str,
        date_str: str,
        items: list[CuratedArticle],
        message_id: str,
        llm_model: str,
        tokens_used: int,
        cost_rmb: float,
        auxiliary_matches: int = 0,
    ) -> None:
        """Record that a digest was successfully sent."""
        history = self.load_history()

        # Build by_type counts
        by_type: dict[str, int] = {}
        for item in items:
            ct = item.content_type.value
            by_type[ct] = by_type.get(ct, 0) + 1

        record = DigestRecord(
            digest_type=digest_type,
            date=date_str,
            items_count=len(items),
            by_type=by_type,
            auxiliary_matches=auxiliary_matches,
            message_id=message_id,
            sent_at=datetime.now(),
            llm_model=llm_model,
            tokens_used=tokens_used,
            cost_rmb=cost_rmb,
        )

        history.digests.append(record)

    def get_recent_digests(self, count: int = 7) -> list[DigestRecord]:
        """Get the N most recent digest records."""
        history = self.load_history()
        return history.digests[-count:]

    # ------------------------------------------------------------------
    # Curated Archive (for trend analysis)
    # ------------------------------------------------------------------

    def archive_curated_items(
        self,
        items: list[CuratedArticle],
        week_label: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """Save curated items to a weekly archive file."""
        archive_items: list[ArchiveItem] = []
        category_counts: dict[str, int] = {}
        content_type_counts: dict[str, int] = {}

        for item in items:
            archive_items.append(ArchiveItem(
                title=item.original.title,
                url=item.original.url,
                source=item.original.source,
                content_type=item.content_type.value,
                chinese_title=item.chinese_title,
                chinese_summary=item.chinese_summary,
                categories=item.categories,
                importance_score=item.importance_score,
                weighted_score=item.weighted_score,
                recommendation_reason=item.recommendation_reason,
                install_command=item.install_command,
                curation_date=item.curation_time.strftime("%Y-%m-%d"),
            ))

            # Count categories
            for cat in item.categories:
                category_counts[cat] = category_counts.get(cat, 0) + 1

            # Count content types
            ct = item.content_type.value
            content_type_counts[ct] = content_type_counts.get(ct, 0) + 1

        archive = WeeklyArchive(
            week=week_label,
            start_date=start_date,
            end_date=end_date,
            items=archive_items,
            category_counts=category_counts,
            content_type_counts=content_type_counts,
        )

        archive_path = self.archive_dir / f"{week_label}.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    def get_items_for_period(
        self, start_date: str, end_date: str
    ) -> list[ArchiveItem]:
        """Retrieve archived items within a date range (for trend analysis)."""
        items: list[ArchiveItem] = []
        if not self.archive_dir.exists():
            return items

        for archive_file in sorted(self.archive_dir.glob("*.json")):
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                archive = WeeklyArchive(**data)

                # Check overlap with requested period
                if archive.end_date >= start_date and archive.start_date <= end_date:
                    # Filter items within the exact date range
                    for item in archive.items:
                        if start_date <= item.curation_date <= end_date:
                            items.append(item)
            except Exception:
                continue

        return items

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_seen_urls(self) -> None:
        """Write seen_urls to disk."""
        if self._seen_urls is None:
            return

        # Auto-prune before saving
        self.prune_seen_urls()

        with open(self.seen_urls_path, "w", encoding="utf-8") as f:
            json.dump(
                self._seen_urls.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

    def save_history(self) -> None:
        """Write digest history to disk."""
        if self._history is None:
            return

        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(
                self._history.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

    def save_all(self) -> None:
        """Persist all state to disk."""
        self.save_seen_urls()
        self.save_history()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics for status reporting."""
        store = self.load_seen_urls()
        history = self.load_history()

        # Content type distribution in seen URLs
        ct_counts: dict[str, int] = {}
        for entry in store.urls.values():
            ct = entry.content_type or "unknown"
            ct_counts[ct] = ct_counts.get(ct, 0) + 1

        # Recent digest counts
        daily_count = sum(
            1 for d in history.digests if d.digest_type == "daily"
        )
        weekly_count = sum(
            1 for d in history.digests if d.digest_type == "weekly"
        )
        monthly_count = sum(
            1 for d in history.digests if d.digest_type == "monthly"
        )

        return {
            "total_unique_urls": store.stats.total_unique_urls,
            "last_pruned": (
                store.stats.last_pruned.isoformat()
                if store.stats.last_pruned
                else None
            ),
            "content_type_distribution": ct_counts,
            "total_digests_sent": len(history.digests),
            "digests_by_type": {
                "daily": daily_count,
                "weekly": weekly_count,
                "monthly": monthly_count,
            },
            "archive_weeks": len(list(self.archive_dir.glob("*.json")))
            if self.archive_dir.exists()
            else 0,
        }
