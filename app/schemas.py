"""Shapes of the data the API sends back (validated by Pydantic)."""

from typing import Literal

from pydantic import BaseModel

Country = Literal["UK", "US"]


class Occupation(BaseModel):
    id: int
    country: Country
    code: str
    title: str
    median_pay: float | None
    currency: str
    growth_pct: float | None
    education: str | None
    employment: int | None
    source: str


class OccupationPage(BaseModel):
    items: list[Occupation]
    total: int
    page: int
    page_size: int
