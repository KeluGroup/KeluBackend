from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class FormSubmission(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)