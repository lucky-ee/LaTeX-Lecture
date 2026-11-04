"""Request and response models for the interpretation API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "math"]
    content: str
    readings: list[str]


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[Segment]
