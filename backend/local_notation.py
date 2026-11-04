"""Inputs answered locally, without calling the LLM."""

from schemas import Interpretation, Segment

_KNOWN_NOTATION = {
    "(x^2)/2": [r"\frac{x^2}{2}"],
    "(1+x^2)/2": [r"\frac{1+x^2}{2}", r"1+\frac{x^2}{2}"],
}


def known_wispr_notation(text: str) -> Interpretation | None:
    compact = "".join(text.lower().split())
    options = _KNOWN_NOTATION.get(compact)
    if options is None:
        return None
    return Interpretation(segments=[Segment(kind="math", content=text, readings=options)])
