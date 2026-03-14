from __future__ import annotations

from app.security.redaction import redact_text


def test_redact_text_hides_secrets() -> None:
    content = "api_key=super-secret bearer token123"
    redacted = redact_text(content, ["super-secret", "token123"])
    assert "super-secret" not in redacted
    assert "token123" not in redacted
    assert "[REDACTED]" in redacted
