"""Answer extraction from synthesized model output.

The benchmark prompts ask the chairman to emit a final line like
    FINAL ANSWER: B
We try progressively looser regex patterns to be robust to variations
in how models format that line (bold, parens, lowercase, etc).
"""
from __future__ import annotations

import re


# ── MCQ ────────────────────────────────────────────────────────────────
# Try the most specific patterns first, then fall back to looser ones.
# Each pattern requires the captured letter to be followed by a non-letter
# (punctuation, whitespace, or end of string) so we don't grab the 'c' out
# of "clearly" or the 'a' out of "answer".
_MCQ_PATTERNS = [
    re.compile(r"FINAL\s+ANSWER\s*[:\-]\s*\*?\*?\(?([A-J])\)?(?![A-Za-z])", re.IGNORECASE),
    re.compile(r"\*\*FINAL\s+ANSWER\*\*\s*[:\-]\s*\(?([A-J])\)?(?![A-Za-z])", re.IGNORECASE),
    re.compile(r"\banswer\s+is\s*\(?([A-J])\)?(?![A-Za-z])", re.IGNORECASE),
    re.compile(r"\bcorrect\s+answer\s*[:\-]?\s*\(?([A-J])\)?(?![A-Za-z])", re.IGNORECASE),
]

# Very last resort: standalone letter on its own line at the end of the output.
_MCQ_TRAILING_LETTER = re.compile(
    r"(?:^|\n)\s*\(?([A-J])\)?\s*[.)]?\s*$",
    re.MULTILINE,
)

# ── Numeric ────────────────────────────────────────────────────────────
_NUMERIC_PATTERN = re.compile(
    r"FINAL\s+ANSWER\s*[:\-]\s*(-?\d+(?:\.\d+)?(?:/\d+)?)",
    re.IGNORECASE,
)

# ── Code ───────────────────────────────────────────────────────────────
_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)\n```", re.DOTALL)


def parse_answer(output: str, question_type: str) -> str | None:
    """Extract the final answer from raw model output.

    Returns None if no answer could be extracted. The caller decides how
    to treat that (record as a parse failure, mark as incorrect, etc).
    """
    if not output:
        return None

    if question_type == "mcq":
        for pattern in _MCQ_PATTERNS:
            match = pattern.search(output)
            if match:
                return match.group(1).upper()
        trailing = _MCQ_TRAILING_LETTER.findall(output.strip())
        if trailing:
            return trailing[-1].upper()
        return None

    if question_type == "numeric":
        match = _NUMERIC_PATTERN.search(output)
        if match:
            return match.group(1).strip()
        return None

    if question_type == "code":
        blocks = _CODE_BLOCK.findall(output)
        if blocks:
            # Last code block is usually the final answer
            return blocks[-1].strip()
        return None

    return None
