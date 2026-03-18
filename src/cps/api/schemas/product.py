"""Product request/response schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProductItem(BaseModel):
    """Product list item."""
    id: int
    platform_id: str
    platform: str
    title: str | None
    category: str | None
    is_active: bool
    first_seen: datetime
    updated_at: datetime
    current_price: int | None = None  # cents, from price_summary

    model_config = {"from_attributes": True}


class PricePoint(BaseModel):
    recorded_date: date
    price_cents: int
    price_type: str


class FetchRunItem(BaseModel):
    id: int
    status: str
    points_extracted: int | None
    ocr_confidence: float | None
    validation_passed: bool | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    """Full product detail for side drawer."""
    id: int
    platform_id: str
    platform: str
    url: str | None
    title: str | None
    category: str | None
    is_active: bool
    first_seen: datetime
    updated_at: datetime
    lowest_price: int | None = None
    highest_price: int | None = None
    current_price: int | None = None

    model_config = {"from_attributes": True}


class AddProductRequest(BaseModel):
    platform_id: str = Field(min_length=10, max_length=11, pattern=r"^[A-Za-z0-9]+$")
    platform: str = Field(default="amazon", max_length=30)


class BatchAddRequest(BaseModel):
    items: list[AddProductRequest] = Field(max_length=500)


class UpdateProductRequest(BaseModel):
    is_active: bool | None = None
    title: str | None = None
    category: str | None = None


class BatchUpdateRequest(BaseModel):
    ids: list[int] = Field(max_length=500)
    action: Literal["activate", "deactivate"]


class DeleteProductRequest(BaseModel):
    confirm: bool
