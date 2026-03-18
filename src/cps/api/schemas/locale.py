"""Locale update request schema."""

from typing import Literal
from pydantic import BaseModel


class LocaleUpdateRequest(BaseModel):
    locale: Literal["zh-CN", "en-US", "es-ES"]
