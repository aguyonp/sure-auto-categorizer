"""Entry point: periodically categorize uncategorized Sure transactions with an LLM."""

from __future__ import annotations

import signal
import sys
import time
from types import FrameType

from loguru import logger
from pydantic import ValidationError

from app.categorizer import Categorizer
from app.config import Settings
from app.sure import SureClient, Transaction

_stop = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _stop
    logger.info("Received signal {}, shutting down after current run", signum)
    _stop = True


def _batched(items: list[Transaction], size: int) -> list[list[Transaction]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_once(settings: Settings) -> None:
    """Single pass: fetch uncategorized transactions and assign categories."""
    with SureClient(settings.sure_base, settings.sure_api_key, settings.request_timeout) as sure:
        categories = sure.categories()
        if not categories:
            logger.warning("No categories defined in Sure; nothing to assign")
            return

        pending = sure.uncategorized_transactions(settings.sure_account_id)
        logger.info("Found {} uncategorized transactions", len(pending))
        if not pending:
            return

        applied = 0
        with Categorizer(
            settings.groq_api_key, settings.groq_url, settings.groq_model, settings.request_timeout
        ) as cat:
            for batch in _batched(pending, settings.batch_size):
                try:
                    assignments = cat.categorize(batch, categories)
                except Exception as exc:  # noqa: BLE001 - isolate batch failures
                    logger.error("Categorization failed for a batch: {}", exc)
                    continue

                by_id = {t.id: t for t in batch}
                for txn_id, cat_id in assignments.items():
                    txn = by_id[txn_id]
                    cat_name = next((c.name for c in categories if c.id == cat_id), cat_id)
                    if settings.dry_run:
                        logger.info("[dry-run] {!r} -> {}", txn.name, cat_name)
                        continue
                    try:
                        sure.set_category(txn_id, cat_id)
                        applied += 1
                        logger.info("{!r} -> {}", txn.name, cat_name)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed to update transaction {}: {}", txn_id, exc)

        logger.info("Run complete: {} transaction(s) categorized", applied)


def main() -> int:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.error("Invalid configuration:\n{}", exc)
        return 2

    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.upper(), backtrace=False, diagnose=False)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "Starting Sure auto-categorizer (model={}, interval={}s, dry_run={})",
        settings.groq_model,
        settings.run_interval_seconds,
        settings.dry_run,
    )

    while not _stop:
        try:
            run_once(settings)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.exception("Unexpected error during run: {}", exc)

        if settings.run_interval_seconds == 0 or _stop:
            break

        logger.info("Sleeping {}s until next run", settings.run_interval_seconds)
        for _ in range(settings.run_interval_seconds):
            if _stop:
                break
            time.sleep(1)

    logger.info("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
