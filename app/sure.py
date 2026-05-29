"""Thin client for the Sure Finance (Maybe-compatible) REST API."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass(slots=True)
class Category:
    id: str
    name: str
    classification: str | None  # "income" | "expense" | None


@dataclass(slots=True)
class Transaction:
    id: str
    name: str
    classification: str  # "income" | "expense"
    amount: str
    account_name: str


_RETRY = dict(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)


class SureClient:
    """Synchronous Sure API client. Use as a context manager."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            base_url=f"{base_url}/api/v1",
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    def __enter__(self) -> "SureClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @retry(**_RETRY)
    def _get(self, path: str, **params: object) -> dict:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(**_RETRY)
    def _patch(self, path: str, json: dict) -> dict:
        resp = self._client.patch(path, json=json)
        resp.raise_for_status()
        return resp.json()

    def categories(self) -> list[Category]:
        data = self._get("/categories")
        return [
            Category(id=c["id"], name=c["name"], classification=c.get("classification"))
            for c in data.get("categories", [])
        ]

    def uncategorized_transactions(self, account_id: str | None = None) -> list[Transaction]:
        """Return every transaction that has no category yet, across all pages."""
        out: list[Transaction] = []
        page = 1
        while True:
            params: dict[str, object] = {"page": page, "per_page": 100}
            if account_id:
                params["account_id"] = account_id
            data = self._get("/transactions", **params)
            txns = data.get("transactions", [])
            for t in txns:
                if t.get("category") is None and t.get("transfer") is None:
                    out.append(
                        Transaction(
                            id=t["id"],
                            name=t.get("name") or t.get("notes") or "",
                            classification=t.get("classification", "expense"),
                            amount=t.get("amount", ""),
                            account_name=(t.get("account") or {}).get("name", ""),
                        )
                    )
            pagination = data.get("pagination", {})
            if page >= pagination.get("total_pages", 1) or not txns:
                break
            page += 1
        return out

    def set_category(self, transaction_id: str, category_id: str) -> None:
        self._patch(f"/transactions/{transaction_id}", json={"transaction": {"category_id": category_id}})
        logger.debug("Set category {} on transaction {}", category_id, transaction_id)
