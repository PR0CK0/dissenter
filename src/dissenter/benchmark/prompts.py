"""Benchmark-specific instructions appended to each question.

The dissenter engine is unchanged — we just wrap the question text with
instructions that tell the chairman (and debate models) to end their
final response with a parseable line.
"""
from __future__ import annotations

from .datasets import Question


_MCQ_INSTRUCTION = """

---
IMPORTANT — BENCHMARK MODE:
You are being evaluated on a multiple-choice question with a single correct
answer. After any reasoning or discussion, the final response MUST end with
this exact line (no extra text after it):

FINAL ANSWER: <letter>

Where <letter> is a single uppercase letter (A, B, C, D, ...) identifying
the correct choice. Do not include explanations after this line.
"""

_NUMERIC_INSTRUCTION = """

---
IMPORTANT — BENCHMARK MODE:
You are being evaluated on a numeric-answer question. After any reasoning,
the final response MUST end with this exact line (no extra text after it):

FINAL ANSWER: <number>

Where <number> is the numeric answer with no units or extra text.
"""

_CODE_INSTRUCTION = """

---
IMPORTANT — BENCHMARK MODE:
You are being evaluated on a coding task. Provide a single Python code block
containing a complete standalone function that solves the problem exactly as
described. The final Python code block in your response is the submission:

```python
def solution(...):
    ...
```
"""


def format_benchmark_question(q: Question) -> str:
    """Return the full question text to send into the debate engine.

    MCQ questions get the choices inlined below the question text.
    All types get a format-specific instruction appended.
    """
    parts = [q.question]

    if q.type == "mcq" and q.choices:
        parts.append("")
        for letter in sorted(q.choices.keys()):
            parts.append(f"{letter}. {q.choices[letter]}")
        parts.append(_MCQ_INSTRUCTION)
    elif q.type == "mcq":
        parts.append(_MCQ_INSTRUCTION)
    elif q.type == "numeric":
        parts.append(_NUMERIC_INSTRUCTION)
    elif q.type == "code":
        parts.append(_CODE_INSTRUCTION)

    return "\n".join(parts)
