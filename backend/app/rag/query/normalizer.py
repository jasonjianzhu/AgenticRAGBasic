"""Query normalization: fullwidth→halfwidth, whitespace cleanup."""
from __future__ import annotations

import re
import unicodedata


class QueryNormalizer:
    """Normalize user queries for consistent processing.

    Transformations:
    - Fullwidth characters → halfwidth (e.g. Ａ→A, ０→0, ？→?)
    - Multiple spaces/tabs → single space
    - Strip leading/trailing whitespace
    """

    def normalize(self, query: str) -> str:
        """Normalize a query string."""
        if not query:
            return query

        # Fullwidth → halfwidth
        result = self._fullwidth_to_halfwidth(query)

        # Collapse whitespace
        result = re.sub(r"[ \t]+", " ", result)

        # Strip
        result = result.strip()

        return result

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """Convert fullwidth ASCII characters to halfwidth."""
        chars = []
        for ch in text:
            code = ord(ch)
            # Fullwidth ASCII variants: U+FF01 (！) to U+FF5E (～)
            # map to U+0021 (!) to U+007E (~)
            if 0xFF01 <= code <= 0xFF5E:
                chars.append(chr(code - 0xFEE0))
            # Fullwidth space U+3000 → regular space
            elif code == 0x3000:
                chars.append(" ")
            else:
                chars.append(ch)
        return "".join(chars)
