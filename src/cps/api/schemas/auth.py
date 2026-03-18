"""Auth request/response schemas."""

from datetime import datetime
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    locale: str
    created_at: datetime
    model_config = {"from_attributes": True}
