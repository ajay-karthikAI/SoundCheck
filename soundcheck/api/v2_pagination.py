"""Opaque, validated offset cursors for API v2 result pages."""

from __future__ import annotations

import base64
import binascii


def encode_cursor(offset: int) -> str:
    """Encode the next zero-based offset without exposing it as a query field."""
    payload = f"soundcheck-v2:{offset}".encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    """Decode an opaque cursor or raise ValueError for a typed 422."""
    if cursor is None:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.urlsafe_b64decode(cursor + padding).decode()
        prefix, value = payload.split(":", maxsplit=1)
        offset = int(value)
    except (UnicodeDecodeError, ValueError, binascii.Error) as error:
        raise ValueError("invalid cursor") from error
    if prefix != "soundcheck-v2" or offset < 0:
        raise ValueError("invalid cursor")
    return offset
