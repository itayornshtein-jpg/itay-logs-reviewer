"""Coralogix search client."""
from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_DOMAIN = "api.coralogix.com"
API_KEY_ENV = "CORALOGIX_API_KEY"
DOMAIN_ENV = "CORALOGIX_DOMAIN"


class CoralogixError(Exception):
    """Raised when Coralogix communication fails."""


def _clean_string(value: str, *, max_length: int = 2048) -> str:
    cleaned = " ".join(str(value).split())
    return cleaned[:max_length]


def _validate_timeframe(timeframe: Dict[str, Any]) -> Dict[str, str]:
    if not isinstance(timeframe, dict):
        raise ValueError("timeframe must be a mapping with 'from' and 'to' keys")

    start = timeframe.get("from")
    end = timeframe.get("to")
    if not start or not end:
        raise ValueError("timeframe requires both 'from' and 'to' values")

    return {"from": _clean_string(start, max_length=128), "to": _clean_string(end, max_length=128)}


def _validate_pagination(pagination: Dict[str, Any]) -> Dict[str, int]:
    if not isinstance(pagination, dict):
        raise ValueError("pagination must be a mapping with numeric values")

    cleaned: Dict[str, int] = {}

    def _validate_positive(name: str, raw: Any, *, allow_zero: bool = False) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"pagination {name} must be an integer") from None
        if allow_zero:
            if value < 0:
                raise ValueError(f"pagination {name} cannot be negative")
        elif value <= 0:
            raise ValueError(f"pagination {name} must be positive")
        return value

    if "limit" in pagination:
        cleaned["limit"] = min(_validate_positive("limit", pagination.get("limit")), 500)

    if "offset" in pagination:
        cleaned["offset"] = _validate_positive("offset", pagination.get("offset"), allow_zero=True)

    if "page" in pagination:
        cleaned["page"] = _validate_positive("page", pagination.get("page"))

    if "pageSize" in pagination or "page_size" in pagination:
        size_value = pagination.get("pageSize", pagination.get("page_size"))
        cleaned["pageSize"] = min(_validate_positive("page size", size_value), 500)

    return cleaned


def search_logs(
    query: str,
    timeframe: Dict[str, Any],
    *,
    filters: Dict[str, Any] | None = None,
    pagination: Dict[str, Any] | None = None,
    domain: str | None = None,
    api_key: str | None = None,
    timeout: int | float = 10,
) -> Dict[str, Any]:
    """Execute a Coralogix search request.

    Parameters
    ----------
    query: str
        Search query text.
    timeframe: dict
        Dictionary containing ``from`` and ``to`` ISO strings or timestamps.
    filters: dict, optional
        Additional filters forwarded to Coralogix.
    pagination: dict, optional
        Optional pagination controls such as limit/offset or page/pageSize.
    domain: str, optional
        Override the Coralogix domain (defaults to CORALOGIX_DOMAIN env var or the public endpoint).
    api_key: str, optional
        Override the API key (defaults to CORALOGIX_API_KEY env var).
    timeout: int | float
        Timeout in seconds for the HTTP request.
    """

    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        raise CoralogixError("Coralogix API key is not configured")

    sanitized_query = _clean_string(query)
    sanitized_timeframe = _validate_timeframe(timeframe)

    payload: Dict[str, Any] = {"query": sanitized_query, "timeframe": sanitized_timeframe}
    if filters:
        if not isinstance(filters, dict):
            raise ValueError("filters must be a mapping")
        payload["filters"] = {str(k): v for k, v in filters.items()}

    if pagination:
        payload["pagination"] = _validate_pagination(pagination)

    target_domain = domain or os.environ.get(DOMAIN_ENV) or DEFAULT_DOMAIN
    url = f"https://{target_domain}/api/v1/logs/search"

    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - exercised via URLError path in tests
        raise CoralogixError(f"Coralogix request failed with status {exc.code}") from None
    except URLError as exc:
        raise CoralogixError(f"Failed to reach Coralogix: {exc.reason}") from None

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise CoralogixError("Coralogix returned invalid JSON") from exc
