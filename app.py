from fastapi import FastAPI, HTTPException, Request, APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import logging
import os


app = FastAPI()
logger = logging.getLogger(__name__)
API_SECRET = os.getenv("FORM_API_SECRET") #python -c "import secrets; print(secrets.token_hex(32))"


def verify_api_key(request: Request) -> None:
    key = request.headers.get("x-api-key")
    if not key or key != API_SECRET:
        raise HTTPException(status_code=403, detail={"success": False, "status_code": 403, "message": "Forbidden"})

protected_router = APIRouter(dependencies=[Depends(verify_api_key)])
app.include_router(protected_router)

class FormSubmission(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)


def build_exception(status_code: int, detail: str, exc: Exception) -> HTTPException:
    if status_code >= 500:
        logger.exception("Server error [%s]: %s", status_code, exc)
    else:
        logger.warning("Client/upstream error [%s]: %s", status_code, exc)
    return HTTPException(status_code=status_code, detail=detail)


def send_to_airtable(data: dict) -> dict:
    message = data.get("message", "").lower()

    if "test-fail-401" in message:
        raise PermissionError("Airtable API key invalid or missing")
    if "test-fail-503" in message:
        raise TimeoutError("Airtable request timed out")
    if "test-fail-400" in message:
        raise ValueError("Airtable rejected the payload structure")
    if "test-fail-500" in message:
        raise RuntimeError("Unexpected Airtable internal error")

    return {
        "id": "rec_dummy_123",
        "status": "created",
        "received": data
    }

def build_success_response(payload: FormSubmission, airtable_response: dict) -> dict:
    return {
        "success": True,
        "status_code": 200,
        "message": "Form submission received",
        "airtable": airtable_response
    }


@app.get("/")
def health():
    return {"ok": True}

@app.get("/api/health")
def api_health():
    return {"status": "healthy"}

@protected_router.post("/api/formsubmit")
def form_submit(payload: FormSubmission, request: Request):
    
    try:
        airtable_response = send_to_airtable(payload.model_dump())
        return build_success_response(payload, airtable_response)

    except HTTPException:
        raise

    except PermissionError as exc:
        raise build_exception(502, "Submission service authentication failed", exc) from exc

    except TimeoutError as exc:
        raise build_exception(503, "Submission service temporarily unavailable", exc) from exc

    except ValueError as exc:
        raise build_exception(502, "Submission service rejected the request", exc) from exc

    except Exception as exc:
        raise build_exception(500, "Internal server error", exc) from exc