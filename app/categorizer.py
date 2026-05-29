"""LLM-backed categorization via Groq's OpenAI-compatible chat API."""

from __future__ import annotations

import json

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.sure import Category, Transaction

_SYSTEM_PROMPT = (
    "You are a precise personal-finance assistant. You assign exactly one category to each "
    "bank transaction, choosing only from the provided category list. Transaction labels are "
    "often French bank wording (e.g. 'CB', 'VIR', 'PRLV', 'RETRAIT'). Use the merchant or "
    "wording and the income/expense nature to decide. If no category clearly fits, return null "
    "for that transaction rather than guessing."
)


class Categorizer:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Categorizer":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    def _complete(self, messages: list[dict]) -> str:
        resp = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": messages,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def categorize(
        self, transactions: list[Transaction], categories: list[Category]
    ) -> dict[str, str]:
        """Map transaction id -> category id. Unmatched transactions are omitted."""
        if not transactions:
            return {}

        name_to_id = {c.name: c.id for c in categories}
        category_names = sorted(name_to_id)

        items = [
            {"id": t.id, "label": t.name, "type": t.classification, "amount": t.amount}
            for t in transactions
        ]
        user_prompt = (
            "Allowed categories (use the exact name):\n"
            + "\n".join(f"- {n}" for n in category_names)
            + "\n\nTransactions to categorize:\n"
            + json.dumps(items, ensure_ascii=False)
            + '\n\nReturn JSON of the form {"assignments": [{"id": "<txn id>", '
            '"category": "<exact category name or null>"}]}. Include every transaction id exactly once.'
        )

        raw = self._complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON output; skipping this batch")
            return {}

        result: dict[str, str] = {}
        valid_ids = {t.id for t in transactions}
        for a in parsed.get("assignments", []):
            txn_id = a.get("id")
            cat_name = a.get("category")
            if txn_id not in valid_ids or not cat_name:
                continue
            cat_id = name_to_id.get(cat_name)
            if cat_id is None:
                logger.warning("LLM proposed unknown category {!r}; ignoring", cat_name)
                continue
            result[txn_id] = cat_id
        return result
