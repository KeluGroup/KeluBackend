from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class FormSubmission(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)
    service: str = Field(..., min_length=1, max_length=100)


class AdminLogin(BaseModel):
    password: str


class LeadStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(Nuevo|Contactado|En proceso|Atendido)$")


class ContentTrigger(BaseModel):
    """Body opcional del POST /api/cron/kelu-receta para forzar un contenido puntual."""
    content_type: Optional[str] = Field(default=None, pattern="^(weekly_recipe|midweek_tip_dato|midweek_tip_foto)$")
    index: Optional[int] = Field(default=None, ge=0)