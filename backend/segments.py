"""Clean-up of the segment list the model returns."""

import re

from schemas import Segment


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Match the phrase case-insensitively and with any run of whitespace between words.
    return re.compile(r"\s+".join(re.escape(word) for word in phrase.split()), re.IGNORECASE)


def remove_repeated_math(segments: list[Segment]) -> list[Segment]:
    """Remove a math phrase the model also left in the text segment before it.

    The model sometimes returns the whole sentence as text and then the spoken
    math again as a math segment, so the phrase shows up twice. When the text
    segment just before a math segment contains that segment's phrase, the
    phrase is cut out of the text, and any words after it move to after the math.
    """
    cleaned: list[Segment] = []
    for segment in segments:
        previous = cleaned[-1] if cleaned else None
        if (
            segment.kind == "math"
            and segment.readings
            and segment.content.strip()
            and previous is not None
            and previous.kind == "text"
        ):
            matches = list(_phrase_pattern(segment.content).finditer(previous.content))
            if matches:
                last = matches[-1]
                before, after = previous.content[: last.start()], previous.content[last.end():]
                cleaned.pop()
                if before.strip():
                    cleaned.append(Segment(kind="text", content=before, readings=[]))
                cleaned.append(segment)
                if after.strip():
                    cleaned.append(Segment(kind="text", content=after, readings=[]))
                continue
        cleaned.append(segment)
    return cleaned
