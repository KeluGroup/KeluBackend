from fastapi import FastAPI, HTTPException, Request, APIRouter, Depends
from pydantic import BaseModel, Field
from pyairtable import Api
from schemas.models import FormSubmission
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware

import bcrypt
import logging
import os
import json
import hmac
import hashlib
import base64
import time

# Default to ["*"] so the API works in production without extra config.
# Real security comes from the x-api-key header check.
ALLOWED_ORIGINS = json.loads(os.getenv("ALLOWED_ORIGINS", '["*"]'))


app = FastAPI(    
    title="Kelu API",
    docs_url=None,
    redoc_url="/redoc",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET", "PATCH", "OPTIONS"],
    allow_headers=["x-api-key", "Content-Type", "x-admin-token", "application/json"],
)


logger = logging.getLogger(__name__)
API_SECRET     = os.getenv("FORM_API_SECRET")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").encode("utf-8")  # bcrypt hash

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Custom /docs with favicon ──────────────────────────
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Docs",
        swagger_favicon_url="/static/favicon.svg",
    )


def verify_api_key(request: Request) -> None:
    key = request.headers.get("x-api-key")
    if not key or key != API_SECRET:
        raise HTTPException(status_code=403, detail={"success": False, "status_code": 403, "message": "Forbidden"})

# ── Admin token (HMAC, valid ~2 hours, no extra deps) ──────────────
def _make_token(hour_offset: int = 0) -> str:
    slot = str(int(time.time()) // 3600 + hour_offset)
    sig  = hmac.new(ADMIN_PASSWORD.encode(), slot.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode()

def verify_admin_token(request: Request) -> None:
    token = request.headers.get("x-admin-token", "")
    if not token or not ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Accept current hour and the one before (overlap on boundary)
    valid = any(hmac.compare_digest(token, _make_token(offset)) for offset in [0, -1])
    if not valid:
        raise HTTPException(status_code=403, detail="Forbidden")

class AdminLogin(BaseModel):
    password: str

@app.post("/api/admin/login")
def admin_login(body: AdminLogin):
    if not ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=503, detail="Admin not configured — set ADMIN_PASSWORD_HASH env var")
    if not bcrypt.checkpw(body.password.encode("utf-8"), ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": _make_token()}



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
admin_router     = APIRouter(dependencies=[Depends(verify_admin_token)])

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


class LeadStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(Nuevo|Contactado|En proceso|Atendido)$")

@admin_router.get("/api/admin/leads")
def get_leads():
    try:
        table   = get_airtable_table()
        records = table.all()
        leads   = [
            {
                "id":        r["id"],
                "name":      r["fields"].get("Name", ""),
                "email":     r["fields"].get("Email", ""),
                "company":   r["fields"].get("Company", ""),
                "message":   r["fields"].get("Message", ""),
                "status":    r["fields"].get("Status", "Nuevo"),
                "createdAt": r.get("createdTime", ""),
            }
            for r in records
        ]
        leads.sort(key=lambda x: x["createdAt"], reverse=True)
        return {"success": True, "total": len(leads), "leads": leads}
    except Exception as exc:
        raise build_exception(500, "Failed to fetch leads", exc) from exc

@admin_router.patch("/api/admin/leads/{record_id}")
def update_lead_status(record_id: str, body: LeadStatusUpdate):
    try:
        table = get_airtable_table()
        table.update(record_id, {"Status": body.status})
        return {"success": True, "id": record_id, "Status": body.status}
    except Exception as exc:
        raise build_exception(500, "Failed to update lead status", exc) from exc

app.include_router(protected_router)
app.include_router(admin_router)