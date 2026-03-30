from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


app = FastAPI()


class FormSubmission(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)

@app.get("/")
def health():
    return {"ok": True}

@app.get("/api/health")
def api_health():
    return {"status": "healthy"}


@app.post("/api/formsubmit")
def form_submit(payload: FormSubmission):
    airtable_dummy_response = {
        "id": "rec_dummy_123",
        "status": "created",
        "received": payload.model_dump()
    }

    return {
        "success": True,
        "message": "Form submission received",
        "airtable": airtable_dummy_response
    }