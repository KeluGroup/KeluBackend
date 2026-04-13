from fastapi import APIRouter, Depends, HTTPException


from schemas.models import AdminLogin, LeadStatusUpdate
from core.auth import verify_admin_token, verify_password, _make_token
from services.airtable import fetch_all_leads, update_lead
from core.exceptions import build_exception

router = APIRouter(dependencies=[Depends(verify_admin_token)])


# Login has no admin token dependency — it IS the login
login_router = APIRouter()

@login_router.post("/login")
def admin_login(body: AdminLogin):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": _make_token()}


@router.get("/leads")
def get_leads():
    try:
        leads = fetch_all_leads()
        return {"success": True, "total": len(leads), "leads": leads}
    except Exception as exc:
        raise build_exception(500, "Failed to fetch leads", exc) from exc


@router.patch("/leads/{record_id}")
def update_lead_status(record_id: str, body: LeadStatusUpdate):
    try:
        update_lead(record_id, body.status)
        return {"success": True, "id": record_id, "status": body.status}
    except Exception as exc:
        raise build_exception(500, "Failed to update lead status", exc) from exc