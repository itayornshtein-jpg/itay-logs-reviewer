"""Lightweight ChatGPT SSO integration helpers.

This module keeps the SSO logic self contained and dependency free. It fakes a
connection by consuming configuration from environment variables or explicit
parameters so that the CLI can surface the connection status without hitting
external services.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict

DEFAULT_RESOURCES: Dict[str, object] = {
    "models": ["gpt-4o-mini"],
    "workspace": "default",
    "notes": "Using ChatGPT account resources",
}


@dataclass
class ChatGPTSession:
    """Represents a lightweight SSO connection to ChatGPT."""

    account: str
    resources: Dict[str, object]
    token_hint: str
    connected_at: datetime

    @property
    def resource_summary(self) -> str:
        if not self.resources:
            return "No resources advertised by ChatGPT account"
        compact = []
        for key, value in self.resources.items():
            compact.append(f"{key}: {value}")
        return "; ".join(compact)


def _load_resources_from_env() -> Dict[str, object] | None:
    raw = os.environ.get("CHATGPT_SSO_RESOURCES")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _mask_token(token: str) -> str:
    suffix = token[-4:] if token else ""
    return f"***{suffix}" if suffix else "(no token)"


def connect_chatgpt_via_sso(token: str | None = None, resources: Dict[str, object] | None = None) -> ChatGPTSession:
    """Connect to ChatGPT using an SSO token and expose account resources.

    The function remains offline-only. It validates that a token is present,
    harvests any resource configuration from the environment, and returns a
    session object that callers can use to report the connection status.
    """

    resolved_token = token or os.environ.get("CHATGPT_SSO_TOKEN")
    if not resolved_token:
        raise ValueError("A ChatGPT SSO token is required. Set --chatgpt-sso-token or CHATGPT_SSO_TOKEN.")

    resolved_resources = resources or _load_resources_from_env() or DEFAULT_RESOURCES
    account = os.environ.get("CHATGPT_SSO_ACCOUNT", "chatgpt-user")
    return ChatGPTSession(
        account=account,
        resources=resolved_resources,
        token_hint=_mask_token(resolved_token),
        connected_at=datetime.utcnow(),
    )

