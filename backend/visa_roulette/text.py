"""Shared text helpers."""

import unicodedata


def ascii_upper(text: str) -> str:
    """Fold diacritics to ASCII and upper-case (MÜLLER -> MULLER, JOSÉ -> JOSE)."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").upper()
