"""A rough count of tokens, shared by everything that budgets text (no tokenizer needed)."""


def estimate_tokens(text: str) -> int:
    """About four characters per token: enough to budget a context."""
    return (len(text) + 3) // 4
