from fastapi import FastAPI, HTTPException, Request, APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from pyairtable import Api
from schemas.models import FormSubmission

import logging
import os


app = FastAPI()
logger = logging.getLogger(__name__)
API_SECRET = os.getenv("FORM_API_SECRET") #python -c "import secrets; print(secrets.token_hex(32))"
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")


def verify_api_key(request: Request) -> None:
    key = request.headers.get("x-api-key")
    if not key or key != API_SECRET:
        raise HTTPException(status_code=403, detail={"success": False, "status_code": 403, "message": "Forbidden"})


def build_exception(status_code: int, detail: str, exc: Exception) -> HTTPException:
    if status_code >= 500:
        logger.exception("Server error [%s]: %s", status_code, exc)
    else:
        logger.warning("Client/upstream error [%s]: %s", status_code, exc)
    return HTTPException(status_code=status_code, detail=detail)


def get_airtable_table():
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_NAME:
        raise RuntimeError("Airtable configuration is missing")

    api = Api(AIRTABLE_API_KEY)
    return api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

def send_to_airtable(data: dict) -> dict:
    table = get_airtable_table()

    fields = {
        "Name": data.get("name"),
        "Email": data.get("email"),
        "Company": data.get("company"),
        "Message": data.get("message"),
    }

    record = table.create(fields)

    return {
        "id": record.get("id"),
        "status": "created",
        "received": record.get("fields", {})
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

protected_router = APIRouter(dependencies=[Depends(verify_api_key)])

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
    
    except ConnectionError as exc:
        raise build_exception(503, "Submission service unreachable", exc) from exc

    except ValueError as exc:
        raise build_exception(502, "Submission service rejected the request", exc) from exc
    
    except Exception as exc:
        raise build_exception(500, "Internal server error", exc) from exc
    
app.include_router(protected_router)