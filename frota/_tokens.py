"""Shared token estimation used by every frota subcommand."""

# Rough estimate for English prompt text: ~4 characters per token.
TOKENS_PER_CHAR = 0.25


def estimate_tokens(text: str) -> int:
    """Estimate tokens for a piece of text. Empty text is zero tokens."""
    if not text:
        return 0
    return max(1, int(len(text) * TOKENS_PER_CHAR))
