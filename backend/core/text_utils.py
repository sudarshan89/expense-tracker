import re
from typing import Optional


def normalize_text(text: Optional[str]) -> str:
    """
    Normalize text for matching across the application (services, repositories, etc.).
    - Lowercase
    - Trim
    - Remove punctuation/special characters (keep alphanumeric and spaces)
    - Collapse multiple spaces

    Args:
        text: Input text (None-safe)

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Convert to lowercase and trim
    normalized = text.lower().strip()

    # Remove punctuation and special characters, keep alphanumeric and spaces
    normalized = re.sub(r"[^\w\s]", " ", normalized)

    # Collapse multiple spaces into a single space
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized
