"""Normalizing named entities so variants count together."""

from __future__ import annotations

import re
import unicodedata

_SUFFIX = re.compile(r"(?:'s|’s|,? (?:corp\.?|corporation|inc\.?|ltd\.?|plc|co\.|group|holdings))$")


def term_key(name: str, aliases: dict[str, str]) -> str:
    """Case, possessives, company suffixes and configured aliases ("donald trump" -> "trump")."""
    k = unicodedata.normalize("NFKC", name).strip().lower().strip(" .,;:\"'“”‘’")
    k = _SUFFIX.sub("", k).strip()
    alias = aliases.get(k)
    return alias.lower() if alias else k
