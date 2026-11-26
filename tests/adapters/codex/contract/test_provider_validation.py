"""Custom-provider validation of the Codex adapter (offline probe only).

The probe exercises one canonical reserved id (``openai``); the full reserved
list lives in ``codex/src/providers.ts``. Every other rejection below is a
frozen error code asserted through the probe.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]


def test_reserved_provider_id_rejected(codex_probe) -> None:
    assert codex_probe("reserved-provider") == "RESERVED_PROVIDER_ID"


def test_chat_wire_api_rejected(codex_probe) -> None:
    assert codex_probe("chat-wire-api") == "CHAT_WIRE_API"


def test_secret_env_key_rejected(codex_probe) -> None:
    assert codex_probe("secret-env-key") == "SECRET_IN_ENV_KEY"


def test_auth_env_key_conflict_rejected(codex_probe) -> None:
    assert codex_probe("auth-env-conflict") == "AUTH_ENV_KEY_CONFLICT"


def test_aws_on_custom_provider_rejected(codex_probe) -> None:
    assert codex_probe("aws-custom") == "AWS_ON_CUSTOM_PROVIDER"


def test_newer_provider_key_rejected(codex_probe) -> None:
    assert codex_probe("unsupported-key") == "UNSUPPORTED_KEY"
