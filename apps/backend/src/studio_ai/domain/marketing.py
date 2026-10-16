"""Proposed internal model for marketing_analyst, not an ERP response schema."""
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class PromotionEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str
    collected_at: datetime
    product_id: str
    branch_id: str
    stock: Decimal | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    report_ids: list[str] = Field(default_factory=list)
    # Unknown stock/cost must stay unknown, never be replaced with zero.


class PromotionSuggestion(BaseModel):
    status: str = 'DRAFT'
    hypothesis: str
    evidence: list[PromotionEvidence]
    pending_information: list[str]
    # No executor: a suggestion is not an ERP offer or a published ad.

from datetime import date
from .campaigns import StructuredModel, Text

class Product(StructuredModel):
    id: Text
    name: Text
    category: Text

class Stock(StructuredModel):
    product_id: Text
    quantity: int = Field(ge=0)

class Sales(StructuredModel):
    product_id: Text
    start: date
    end: date
    units: int = Field(ge=0)

